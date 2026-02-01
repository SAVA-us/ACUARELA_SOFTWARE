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
        self.col_maps = {} 
        self._connect()
        self._ensure_structure() # Auto-crear hojas si faltan

    def _connect(self):
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            if "gcp_service_account" not in st.secrets:
                raise ValueError("Faltan secrets [gcp_service_account]")

            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            self.client = gspread.authorize(creds)
            
            sheet_url = st.secrets.get("SHEET_URL")
            if not sheet_url:
                raise ValueError("Falta SHEET_URL en secrets")
                
            self.sheet = self.client.open_by_url(sheet_url)
            logger.info("✅ Conectado a Google Sheets")
        except Exception as e:
            st.error(f"Error crítico de conexión a Sheets: {e}")
            raise e

    def _ensure_structure(self):
        """Crea las pestañas necesarias si no existen, basándose en tus CSVs."""
        # Estructura exacta basada en tus CSVs
        required_sheets = {
            "inventory": ["supplier_name", "quantity", "sale_price", "supplier_id", "min_stock_alert", "updated_at", "purchase_price", "name", "id"],
            "orders": ["id", "timestamp", "title", "price", "payment_method", "customer_name", "status", "completed_at"],
            "orders_items": ["order_id", "order_date", "item_name", "quantity", "sale_price", "purchase_price", "subtotal", "item_id"],
            "suppliers": ["contact_person", "email", "phone", "name", "id"]
        }

        existing_titles = [s.title for s in self.sheet.worksheets()]
        
        for name, headers in required_sheets.items():
            if name not in existing_titles:
                try:
                    ws = self.sheet.add_worksheet(title=name, rows=1000, cols=20)
                    ws.append_row(headers)
                    logger.info(f"Creada hoja faltante: {name}")
                except Exception as e:
                    logger.error(f"No se pudo crear hoja {name}: {e}")

    def _get_worksheet(self, name):
        try:
            return self.sheet.worksheet(name)
        except gspread.WorksheetNotFound:
            # Si falla aunque intentamos crearla, re-intentamos estructura
            self._ensure_structure()
            return self.sheet.worksheet(name)

    def _get_col_index(self, ws, col_name):
        """Encuentra dinámicamente la columna por nombre."""
        sheet_id = ws.title
        # Cache simple
        if sheet_id not in self.col_maps:
            self.col_maps[sheet_id] = {}
        
        # Si no está en cache, buscamos
        if col_name not in self.col_maps[sheet_id]:
            headers = ws.row_values(1)
            # Normalizar headers (strip)
            header_map = {h.strip(): i + 1 for i, h in enumerate(headers)}
            self.col_maps[sheet_id] = header_map
            
        return self.col_maps[sheet_id].get(col_name)

    # --- INVENTARIO ---
    def get_all_inventory_items(self):
        ws = self._get_worksheet("inventory")
        data = ws.get_all_records()
        # Limpieza de datos
        clean_data = []
        for item in data:
            # Convertir ID a string siempre
            item['id'] = str(item.get('id', ''))
            # Asegurar números
            try: item['quantity'] = int(item.get('quantity', 0) or 0)
            except: item['quantity'] = 0
            
            try: item['sale_price'] = float(str(item.get('sale_price', 0)).replace(',',''))
            except: item['sale_price'] = 0.0
            
            clean_data.append(item)
        return clean_data

    def get_inventory_item_details(self, item_id):
        items = self.get_all_inventory_items()
        target = str(item_id).strip()
        for item in items:
            if str(item.get('id')).strip() == target:
                return item
        return None

    def save_inventory_item(self, data, custom_id, is_new=False, details=None):
        ws = self._get_worksheet("inventory")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Datos a guardar
        mapped_data = {
            'id': str(custom_id),
            'name': data.get('name'),
            'quantity': data.get('quantity'),
            'purchase_price': data.get('purchase_price'),
            'sale_price': data.get('sale_price'),
            'min_stock_alert': data.get('min_stock_alert', 5),
            'supplier_name': data.get('supplier_name', ''),
            'updated_at': timestamp,
            'supplier_id': data.get('supplier_id', '')
        }

        if is_new:
            # Escribir en el orden de los headers actuales
            headers = ws.row_values(1)
            row = []
            for h in headers:
                key = h.strip()
                row.append(mapped_data.get(key, ""))
            ws.append_row(row)
        else:
            try:
                # Buscar por ID (que en tu CSV está al final, pero find busca en todo)
                cell = ws.find(str(custom_id))
                row_num = cell.row
                
                # Actualizar celdas mapeadas
                for key, val in mapped_data.items():
                    if key == 'id': continue
                    col = self._get_col_index(ws, key)
                    if col:
                        ws.update_cell(row_num, col, val)
            except gspread.CellNotFound:
                # Si no existe, crear
                self.save_inventory_item(data, custom_id, is_new=True)

    def delete_inventory_item(self, item_id):
        ws = self._get_worksheet("inventory")
        try:
            cell = ws.find(str(item_id))
            ws.delete_rows(cell.row)
        except gspread.CellNotFound:
            pass

    # --- VENTAS ---
    def create_order(self, order_data):
        ws_inv = self._get_worksheet("inventory")
        ws_ord = self._get_worksheet("orders")
        ws_itm = self._get_worksheet("orders_items")
        
        order_id = f"ORD-{int(time.time())}"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alerts = []
        
        # 1. Items y Stock
        itm_headers = ws_itm.row_values(1)
        
        for item in order_data['ingredients']:
            pid = str(item['id'])
            qty = int(item['quantity'])
            
            # Restar stock
            try:
                cell = ws_inv.find(pid)
                col_q = self._get_col_index(ws_inv, 'quantity')
                curr = int(ws_inv.cell(cell.row, col_q).value or 0)
                
                if curr < qty:
                    return False, f"Stock insuficiente: {item['name']}", []
                
                ws_inv.update_cell(cell.row, col_q, curr - qty)
                
                # Alerta
                col_a = self._get_col_index(ws_inv, 'min_stock_alert')
                if col_a:
                    limit = int(ws_inv.cell(cell.row, col_a).value or 0)
                    if 0 < (curr - qty) <= limit:
                        alerts.append(f"Stock bajo: {item['name']}")
                
                # Guardar item
                item_vals = {
                    'order_id': order_id, 'order_date': ts,
                    'item_name': item['name'], 'quantity': qty,
                    'sale_price': item.get('sale_price', 0),
                    'purchase_price': item.get('purchase_price', 0),
                    'subtotal': qty * float(item.get('sale_price', 0)),
                    'item_id': pid
                }
                row_itm = [item_vals.get(h.strip(), "") for h in itm_headers]
                ws_itm.append_row(row_itm)
                
            except gspread.CellNotFound:
                return False, f"Producto {pid} no existe en inventario", []

        # 2. Orden Cabecera
        ord_headers = ws_ord.row_values(1)
        ord_vals = {
            'id': order_id, 'timestamp': ts,
            'title': order_data.get('title'),
            'price': order_data.get('price'),
            'payment_method': order_data.get('payment_method'),
            'customer_name': order_data.get('customer_name'),
            'status': 'completed', 'completed_at': ts
        }
        row_ord = [ord_vals.get(h.strip(), "") for h in ord_headers]
        ws_ord.append_row(row_ord)
        
        return True, "Venta registrada", alerts

    def process_direct_sale(self, items, sale_id_dummy, payment=None):
        data = {
            'title': "Venta Directa",
            'price': sum(i['sale_price'] * i['quantity'] for i in items),
            'ingredients': items,
            'payment_method': payment.get('method', 'efectivo') if payment else 'efectivo',
            'customer_name': payment.get('customer', 'General') if payment else 'General'
        }
        return self.create_order(data)

    def get_orders(self, status=None):
        ws = self._get_worksheet("orders")
        data = ws.get_all_records()
        res = []
        for r in data:
            if status and r.get('status') != status and status != 'completed': continue
            try:
                dt = datetime.strptime(str(r.get('timestamp')), "%Y-%m-%d %H:%M:%S")
            except:
                dt = datetime.now()
            r['timestamp_obj'] = dt.replace(tzinfo=timezone.utc)
            r['ingredients'] = [] 
            res.append(r)
        return sorted(res, key=lambda x: x['timestamp_obj'], reverse=True)

    def get_all_suppliers(self):
        ws = self._get_worksheet("suppliers")
        return ws.get_all_records()

    def add_supplier(self, data):
        ws = self._get_worksheet("suppliers")
        headers = ws.row_values(1)
        # Mapeo simple
        vals = {
            'id': f"SUP-{int(time.time())}",
            'name': data.get('name'), 'contact_person': data.get('contact_person'),
            'email': data.get('email'), 'phone': data.get('phone')
        }
        row = [vals.get(h.strip(), "") for h in headers]
        ws.append_row(row)
