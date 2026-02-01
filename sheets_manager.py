import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import streamlit as st
import logging
from datetime import datetime, timezone
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SheetsManager:
    def __init__(self):
        self.client = None
        self.sheet = None
        self._connect()

    def _connect(self):
        """Conecta a Google Sheets usando los secrets de Streamlit."""
        try:
            # Construir el diccionario de credenciales desde st.secrets
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            
            # Asumimos que el usuario puso el JSON en st.secrets["gcp_service_account"]
            creds_dict = dict(st.secrets["gcp_service_account"])
            
            # gspread requiere que private_key tenga los saltos de línea reales (\n)
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            self.client = gspread.authorize(creds)
            
            sheet_url = st.secrets.get("SHEET_URL")
            if not sheet_url:
                raise ValueError("SHEET_URL no encontrado en secrets.")
                
            self.sheet = self.client.open_by_url(sheet_url)
            logger.info("✅ Conexión exitosa a Google Sheets.")
        except Exception as e:
            logger.error(f"❌ Error conectando a Google Sheets: {e}")
            st.error(f"Error de conexión a la base de datos (Sheets): {e}")

    # --- HELPERS ---
    def _get_worksheet(self, name):
        try:
            return self.sheet.worksheet(name)
        except gspread.WorksheetNotFound:
            # Si no existe, la creamos (básico)
            return self.sheet.add_worksheet(title=name, rows=1000, cols=20)

    def _df_to_dicts(self, df):
        return df.to_dict('records')

    # --- INVENTARIO ---
    def get_all_inventory_items(self):
        """Devuelve todo el inventario como lista de diccionarios."""
        ws = self._get_worksheet("inventory")
        data = ws.get_all_records()
        # Asegurar tipos de datos
        for item in data:
            item['id'] = str(item['id']) # ID siempre string para consistencia
        return data

    def get_inventory_item_details(self, item_id):
        """Busca un item por ID (código de barras)."""
        items = self.get_all_inventory_items()
        for item in items:
            if str(item.get('id')) == str(item_id):
                return item
        return None

    def save_inventory_item(self, data, custom_id, is_new=False, details=None):
        """Guarda o actualiza un producto."""
        ws = self._get_worksheet("inventory")
        
        # Preparar fila
        row_data = [
            str(custom_id),
            data.get('name'),
            int(data.get('quantity', 0)),
            float(data.get('purchase_price', 0.0)),
            float(data.get('sale_price', 0.0)),
            int(data.get('min_stock_alert', 5)),
            data.get('supplier_name', ''),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]

        if is_new:
            # Añadir al final
            ws.append_row(row_data)
        else:
            # Actualizar: Buscar la celda con el ID
            try:
                cell = ws.find(str(custom_id))
                # Actualizar toda la fila (rango A:H)
                # Nota: gspread usa indexación 1-based
                row_num = cell.row
                # Actualizamos celdas específicas para no romper si hay más columnas
                # Actualizar cantidad (Col 3), precios (4, 5), etc.
                ws.update_cell(row_num, 2, data.get('name'))
                ws.update_cell(row_num, 3, int(data.get('quantity')))
                ws.update_cell(row_num, 4, float(data.get('purchase_price')))
                ws.update_cell(row_num, 5, float(data.get('sale_price')))
                ws.update_cell(row_num, 6, int(data.get('min_stock_alert')))
                ws.update_cell(row_num, 7, data.get('supplier_name'))
                ws.update_cell(row_num, 8, row_data[7]) # timestamp
            except gspread.CellNotFound:
                logger.error(f"Item {custom_id} no encontrado para actualizar.")
                ws.append_row(row_data) # Fallback

    def delete_inventory_item(self, item_id):
        ws = self._get_worksheet("inventory")
        try:
            cell = ws.find(str(item_id))
            ws.delete_rows(cell.row)
            logger.info(f"Item {item_id} eliminado de Sheet.")
        except gspread.CellNotFound:
            pass

    # --- VENTAS Y PEDIDOS ---
    def create_order(self, order_data):
        """
        Registra una venta. 
        IMPORTANTE: En Sheets esto debe ser atómico manualmente.
        1. Restar stock en 'inventory'.
        2. Guardar en 'orders'.
        3. Guardar items en 'orders_items'.
        """
        ws_inv = self._get_worksheet("inventory")
        ws_orders = self._get_worksheet("orders")
        ws_items = self._get_worksheet("orders_items")

        # Generar ID único simple basado en timestamp si no existe
        order_id = f"ORD-{int(time.time())}"
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Actualizar Stock (Uno por uno)
        alerts = []
        items_summary_list = []
        
        for item in order_data['ingredients']:
            item_id = str(item['id'])
            qty_sold = int(item['quantity'])
            
            try:
                cell = ws_inv.find(item_id)
                # Cantidad actual está en columna 3
                current_qty = int(ws_inv.cell(cell.row, 3).value)
                new_qty = current_qty - qty_sold
                
                if new_qty < 0:
                    raise ValueError(f"Stock insuficiente para {item['name']}")

                ws_inv.update_cell(cell.row, 3, new_qty)
                
                # Check alerta
                min_stock = int(ws_inv.cell(cell.row, 6).value or 0)
                if 0 < new_qty <= min_stock:
                    alerts.append(f"Stock bajo: {item['name']} ({new_qty})")

                # Guardar en orders_items
                ws_items.append_row([
                    order_id,
                    item_id,
                    item['name'],
                    qty_sold,
                    item.get('sale_price', 0),
                    qty_sold * item.get('sale_price', 0)
                ])
                
                items_summary_list.append(f"{item['name']} (x{qty_sold})")

            except gspread.CellNotFound:
                logger.error(f"ID {item_id} no encontrado al procesar venta.")

        # 2. Guardar Order Header
        ws_orders.append_row([
            order_id,
            order_data.get('title', 'Venta'),
            order_data.get('price', 0),
            'completed', # En sheets asumimos completado directo
            order_data.get('payment_method', 'efectivo'),
            order_data.get('customer_name', 'General'),
            timestamp_str,
            ", ".join(items_summary_list)
        ])

        return True, "Venta registrada en Google Sheets.", alerts

    # Método compatible con la firma antigua de process_direct_sale
    def process_direct_sale(self, items_sold, sale_id_dummy, payment_data=None):
        # Adaptamos los datos al formato de create_order
        order_data = {
            'title': f"Venta Directa",
            'price': sum(i['sale_price'] * i['quantity'] for i in items_sold),
            'ingredients': items_sold,
            'payment_method': payment_data.get('method', 'efectivo') if payment_data else 'efectivo',
            'customer_name': payment_data.get('customer', 'General') if payment_data else 'General'
        }
        return self.create_order(order_data)

    # --- REPORTES Y OTROS ---
    def get_orders(self, status=None):
        ws = self._get_worksheet("orders")
        data = ws.get_all_records()
        
        # Enriquecer datos para compatibilidad con la app
        orders = []
        for row in data:
            if status and row.get('status') != status and status != 'completed': 
                # Si piden 'processing', sheets no suele tener ese estado en este flujo simple
                continue
            
            # Convertir string fecha a objeto datetime
            try:
                dt = datetime.strptime(row['timestamp'], "%Y-%m-%d %H:%M:%S")
            except:
                dt = datetime.now()
            
            # Reconstruir estructura de ingredientes simulada (no detallada para vista rápida)
            # Para detalle completo habría que cruzar con orders_items, pero para la vista general esto basta
            row['ingredients'] = [{'name': 'Ver detalle en hoja items', 'quantity': 0}] 
            row['timestamp_obj'] = dt.replace(tzinfo=timezone.utc)
            row['id'] = row['order_id'] # Alias
            orders.append(row)
            
        return sorted(orders, key=lambda x: x['timestamp_obj'], reverse=True)

    def get_orders_in_date_range(self, start_date, end_date):
        all_orders = self.get_orders()
        filtered = []
        for o in all_orders:
            if start_date <= o['timestamp_obj'] <= end_date:
                filtered.append(o)
        return filtered

    def get_order_count(self):
        ws = self._get_worksheet("orders")
        return len(ws.col_values(1)) - 1 # Restar header

    # --- PROVEEDORES ---
    def add_supplier(self, data):
        ws = self._get_worksheet("suppliers")
        ws.append_row([
            f"SUP-{int(time.time())}",
            data.get('name'),
            data.get('contact_person'),
            data.get('email'),
            data.get('phone')
        ])

    def get_all_suppliers(self):
        ws = self._get_worksheet("suppliers")
        return ws.get_all_records()
