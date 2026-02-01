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
        self.col_maps = {}  # Caché para saber en qué número de columna está cada dato
        self._connect()

    def _connect(self):
        """Conecta a Google Sheets usando los secrets de Streamlit."""
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            
            # Verificar si existen los secrets
            if "gcp_service_account" not in st.secrets:
                raise ValueError("No se encontró la sección [gcp_service_account] en secrets.toml")

            creds_dict = dict(st.secrets["gcp_service_account"])
            
            # Corrección vital para la clave privada
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            self.client = gspread.authorize(creds)
            
            sheet_url = st.secrets.get("SHEET_URL")
            if not sheet_url:
                raise ValueError("Falta 'SHEET_URL' en secrets.toml")
                
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
            st.error(f"⚠️ No se encontró la hoja '{name}'. Asegúrate de que tu Excel tenga las pestañas correctas.")
            raise

    def _get_col_index(self, ws, col_name):
        """Busca dinámicamente el índice (número) de una columna por su nombre en el encabezado."""
        sheet_id = ws.title
        if sheet_id not in self.col_maps:
            headers = ws.row_values(1)
            # Mapa { 'nombre_columna': indice_1_based }
            self.col_maps[sheet_id] = {name.strip(): i + 1 for i, name in enumerate(headers)}
        
        # Intentar buscar
        idx = self.col_maps[sheet_id].get(col_name)
        
        # Si no está, recargar headers por si cambiaron recientemente
        if not idx:
            headers = ws.row_values(1)
            self.col_maps[sheet_id] = {name.strip(): i + 1 for i, name in enumerate(headers)}
            idx = self.col_maps[sheet_id].get(col_name)
            
        if not idx:
            logger.warning(f"Columna '{col_name}' no encontrada en la hoja '{sheet_id}'.")
        return idx

    # --- INVENTARIO ---
    def get_all_inventory_items(self):
        ws = self._get_worksheet("inventory")
        data = ws.get_all_records()
        # Asegurar que los IDs sean strings para comparaciones consistentes
        for item in data:
            item['id'] = str(item['id'])
        return data

    def get_inventory_item_details(self, item_id):
        items = self.get_all_inventory_items()
        item_id_str = str(item_id).strip()
        for item in items:
            if str(item.get('id')).strip() == item_id_str:
                return item
        return None

    def save_inventory_item(self, data, custom_id, is_new=False, details=None):
        ws = self._get_worksheet("inventory")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Mapeamos los datos que vienen de la App a las columnas del CSV
        mapped_data = {
            'id': str(custom_id),
            'name': data.get('name'),
            'quantity': int(data.get('quantity', 0)),
            'purchase_price': float(data.get('purchase_price', 0)),
            'sale_price': float(data.get('sale_price', 0)),
            'min_stock_alert': int(data.get('min_stock_alert', 5)),
            'supplier_name': data.get('supplier_name', ''),
            'updated_at': timestamp,
            'supplier_id': data.get('supplier_id', '')
        }

        if is_new:
            # Para fila nueva, obtenemos headers y ordenamos los datos
            headers = ws.row_values(1)
            new_row = []
            for h in headers:
                key = h.strip()
                new_row.append(mapped_data.get(key, "")) # Si la columna no está en nuestros datos, va vacía
            ws.append_row(new_row)
        else:
            # Actualizar existente
            try:
                cell = ws.find(str(custom_id))
                row = cell.row
                
                # Actualizamos celda por celda usando el mapa de columnas
                for col_name, val in mapped_data.items():
                    if col_name == 'id': continue # No cambiamos el ID
                    col_idx = self._get_col_index(ws, col_name)
                    if col_idx:
                        ws.update_cell(row, col_idx, val)
                        
            except gspread.CellNotFound:
                # Si se marcó como update pero no existe, lo creamos
                self.save_inventory_item(data, custom_id, is_new=True)

    def delete_inventory_item(self, item_id):
        ws = self._get_worksheet("inventory")
        try:
            cell = ws.find(str(item_id))
            ws.delete_rows(cell.row)
        except gspread.CellNotFound:
            pass

    # --- VENTAS Y PEDIDOS ---
    def create_order(self, order_data):
        """
        Registra la venta:
        1. Resta stock en 'inventory'.
        2. Guarda detalle en 'orders_items'.
        3. Guarda cabecera en 'orders'.
        """
        ws_inv = self._get_worksheet("inventory")
        ws_orders = self._get_worksheet("orders")
        ws_items = self._get_worksheet("orders_items")

        order_id = f"ORD-{int(time.time())}" # ID único simple
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        alerts = []
        
        # 1. Procesar Items y Stock
        items_headers = ws_items.row_values(1)
        
        for item in order_data['ingredients']:
            item_id = str(item['id'])
            qty_sold = int(item['quantity'])
            
            # Buscar y restar inventario
            try:
                cell = ws_inv.find(item_id)
                col_qty = self._get_col_index(ws_inv, 'quantity')
                
                # Leer cantidad actual
                current_qty = int(ws_inv.cell(cell.row, col_qty).value or 0)
                new_qty = current_qty - qty_sold
                
                if new_qty < 0:
                    return False, f"Stock insuficiente para '{item['name']}'. Disp: {current_qty}", []

                # Actualizar cantidad
                ws_inv.update_cell(cell.row, col_qty, new_qty)
                
                # Verificar alerta stock bajo
                col_alert = self._get_col_index(ws_inv, 'min_stock_alert')
                if col_alert:
                    min_stock = int(ws_inv.cell(cell.row, col_alert).value or 0)
                    if 0 < new_qty <= min_stock:
                        alerts.append(f"Stock bajo: {item['name']} ({new_qty})")

                # Guardar fila en orders_items
                # Mapeo de datos del item a columnas del CSV orders_items
                item_row_map = {
                    'order_id': order_id,
                    'order_date': timestamp_str,
                    'item_name': item['name'],
                    'item_id': item_id,
                    'quantity': qty_sold,
                    'sale_price': float(item.get('sale_price', 0)),
                    'purchase_price': float(item.get('purchase_price', 0)),
                    'subtotal': qty_sold * float(item.get('sale_price', 0))
                }
                
                row_to_append = []
                for h in items_headers:
                    row_to_append.append(item_row_map.get(h.strip(), ""))
                ws_items.append_row(row_to_append)

            except gspread.CellNotFound:
                return False, f"Producto ID {item_id} no encontrado en hoja 'inventory'.", []

        # 2. Registrar Orden (Cabecera)
        orders_headers = ws_orders.row_values(1)
        
        # Mapeo de datos de la orden a columnas del CSV orders
        order_row_map = {
            'id': order_id,
            'timestamp': timestamp_str,
            'title': order_data.get('title', 'Venta'),
            'price': order_data.get('price', 0),
            'payment_method': order_data.get('payment_method', 'efectivo'),
            'customer_name': order_data.get('customer_name', 'General'),
            'status': 'completed',
            'completed_at': timestamp_str
        }
        
        row_order = []
        for h in orders_headers:
            row_order.append(order_row_map.get(h.strip(), ""))
        
        ws_orders.append_row(row_order)

        return True, "Venta registrada exitosamente en Google Sheets.", alerts

    def process_direct_sale(self, items_sold, sale_id_dummy, payment_data=None):
        # Adaptador para la función que usaba App.py
        order_data = {
            'title': f"Venta Directa",
            'price': sum(i.get('sale_price', 0) * i['quantity'] for i in items_sold),
            'ingredients': items_sold,
            'payment_method': payment_data.get('method', 'efectivo') if payment_data else 'efectivo',
            'customer_name': payment_data.get('customer', 'General') if payment_data else 'General'
        }
        return self.create_order(order_data)

    # --- REPORTES Y LECTURA DE VENTAS ---
    def get_orders(self, status=None):
        ws = self._get_worksheet("orders")
        data = ws.get_all_records()
        orders = []
        for row in data:
            # Filtrado simple por estado
            if status and row.get('status') != status and status != 'completed':
                continue
            
            # Parsear fecha para ordenamiento
            ts_str = str(row.get('timestamp', ''))
            try:
                # Intentar varios formatos por si acaso
                if 'T' in ts_str:
                    dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                else:
                    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except:
                dt = datetime.now()
            
            row['timestamp_obj'] = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
            
            # Simulamos 'ingredients' vacío para que app.py no falle al iterar
            # (Para ver detalles se usa la hoja orders_items en el Excel)
            row['ingredients'] = [] 
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
         # Restamos 1 por el encabezado
         return max(0, len(ws.col_values(1)) - 1)

    # --- PROVEEDORES ---
    def add_supplier(self, data):
        ws = self._get_worksheet("suppliers")
        headers = ws.row_values(1)
        
        mapped_data = {
            'id': f"SUP-{int(time.time())}",
            'name': data.get('name'),
            'contact_person': data.get('contact_person'),
            'email': data.get('email'),
            'phone': data.get('phone')
        }
        
        row = []
        for h in headers:
            row.append(mapped_data.get(h.strip(), ""))
        ws.append_row(row)

    def get_all_suppliers(self):
        ws = self._get_worksheet("suppliers")
        return ws.get_all_records()
