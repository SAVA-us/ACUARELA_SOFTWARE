import pandas as pd
import os
import threading
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import io

DB_FILE = 'SAVA_DB.xlsx'

class DataManager:
    def __init__(self):
        # Lock de hilos para evitar condiciones de carrera (Race Conditions)
        # cuando múltiples usuarios usan Streamlit simultáneamente.
        self.lock = threading.Lock()
        self.file = DB_FILE
        self._ensure_db_exists()

    def _ensure_db_exists(self):
        """Inicializa el archivo Excel maestro si no existe."""
        with self.lock:
            if not os.path.exists(self.file):
                # Estructuras base extraídas de tus archivos CSV de exportación
                df_inv = pd.DataFrame(columns=[
                    'id', 'name', 'purchase_price', 'sale_price', 'quantity', 
                    'supplier_name', 'supplier_id', 'min_stock_alert', 'updated_at'
                ])
                df_ord = pd.DataFrame(columns=[
                    'id', 'timestamp', 'title', 'price', 'payment_method', 
                    'customer_name', 'status', 'completed_at'
                ])
                df_items = pd.DataFrame(columns=[
                    'order_id', 'order_date', 'item_name', 'quantity', 
                    'sale_price', 'purchase_price', 'subtotal'
                ])
                df_supp = pd.DataFrame(columns=[
                    'id', 'name', 'phone', 'email', 'contact_person'
                ])
                
                # Crear un usuario admin seguro por defecto
                df_users = pd.DataFrame({
                    'username': ['admin'],
                    'password': [generate_password_hash("admin123")], # Hash seguro con Salt
                    'role': ['admin'],
                    'name': ['Administrador Principal']
                })

                with pd.ExcelWriter(self.file, engine='openpyxl') as writer:
                    df_inv.to_excel(writer, sheet_name='inventory', index=False)
                    df_ord.to_excel(writer, sheet_name='orders', index=False)
                    df_items.to_excel(writer, sheet_name='orders_items', index=False)
                    df_supp.to_excel(writer, sheet_name='suppliers', index=False)
                    df_users.to_excel(writer, sheet_name='users', index=False)

    def _read_sheet(self, sheet_name):
        """Lee una hoja del Excel. Se asume que el lock ya fue adquirido por el método llamador o es solo lectura."""
        try:
            return pd.read_excel(self.file, sheet_name=sheet_name)
        except Exception as e:
            return pd.DataFrame()

    def _write_sheets(self, sheet_dict):
        """Escribe múltiples hojas al Excel de forma transaccional."""
        # Se necesita abrir el Excel actual, actualizar las hojas especificadas y mantener las demás
        try:
            # Leer todas las hojas actuales para no perder data
            all_sheets = pd.read_excel(self.file, sheet_name=None)
            
            # Actualizar con los nuevos dataframes
            for sheet_name, df in sheet_dict.items():
                all_sheets[sheet_name] = df
                
            with pd.ExcelWriter(self.file, engine='openpyxl') as writer:
                for sheet_name, df in all_sheets.items():
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            return True
        except Exception as e:
            print(f"Error escribiendo DB: {e}")
            return False

    # --- AUTENTICACIÓN ---
    def verify_user(self, username, password):
        df_users = self._read_sheet('users')
        user_row = df_users[df_users['username'] == username]
        
        if not user_row.empty:
            user_dict = user_row.iloc[0].to_dict()
            if check_password_hash(user_dict['password'], password):
                return user_dict
        return None

    # --- INVENTARIO ---
    def get_inventory(self):
        return self._read_sheet('inventory')

    def add_product(self, product_data):
        with self.lock:
            df = self._read_sheet('inventory')
            new_row = pd.DataFrame([product_data])
            df = pd.concat([df, new_row], ignore_index=True)
            self._write_sheets({'inventory': df})

    def update_inventory(self, df_edited):
        with self.lock:
            self._write_sheets({'inventory': df_edited})

    # --- VENTAS (POS) ---
    def register_sale(self, order_id, cart_items, total_price, payment_method, customer_name):
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        with self.lock:
            df_orders = self._read_sheet('orders')
            df_items = self._read_sheet('orders_items')
            df_inventory = self._read_sheet('inventory')

            # 1. Crear Orden
            new_order = {
                'id': order_id, 'timestamp': timestamp_str, 
                'title': f"Venta #{int(timestamp.timestamp())}",
                'price': total_price, 'payment_method': payment_method, 
                'customer_name': customer_name, 'status': 'completed', 
                'completed_at': timestamp_str
            }
            df_orders = pd.concat([df_orders, pd.DataFrame([new_order])], ignore_index=True)

            # 2. Registrar Items y Actualizar Stock
            items_to_add = []
            for item in cart_items:
                items_to_add.append({
                    'order_id': order_id, 'order_date': timestamp_str, 
                    'item_name': item['name'], 'quantity': item['qty'], 
                    'sale_price': item['sale_price'], 
                    'purchase_price': item.get('purchase_price', 0), 
                    'subtotal': item['sale_price'] * item['qty']
                })
                
                # Descuento de stock vectorial
                mask = df_inventory['id'].astype(str) == str(item['id'])
                if mask.any():
                    current_stock = df_inventory.loc[mask, 'quantity'].values[0]
                    df_inventory.loc[mask, 'quantity'] = max(0, current_stock - item['qty'])

            if items_to_add:
                df_items = pd.concat([df_items, pd.DataFrame(items_to_add)], ignore_index=True)
                # Escribir transaccionalmente todo
                self._write_sheets({
                    'orders': df_orders,
                    'orders_items': df_items,
                    'inventory': df_inventory
                })
                return True
        return False

    # --- DASHBOARD Y MÉTRICAS ---
    def get_sales_history(self):
        return self._read_sheet('orders')

    def get_dashboard_metrics(self):
        df_inv = self.get_inventory()
        df_orders = self.get_sales_history()
        
        metrics = {"total_products": 0, "inventory_value": 0, "low_stock": 0, "sales_today": 0}
        
        if not df_inv.empty:
            metrics['total_products'] = len(df_inv)
            # Asegurar numérico para cálculo
            df_inv['quantity'] = pd.to_numeric(df_inv['quantity'], errors='coerce').fillna(0)
            df_inv['sale_price'] = pd.to_numeric(df_inv['sale_price'], errors='coerce').fillna(0)
            df_inv['min_stock_alert'] = pd.to_numeric(df_inv['min_stock_alert'], errors='coerce').fillna(3)
            
            metrics['inventory_value'] = (df_inv['quantity'] * df_inv['sale_price']).sum()
            metrics['low_stock'] = len(df_inv[df_inv['quantity'] <= df_inv['min_stock_alert']])
            
        if not df_orders.empty:
            df_orders['dt'] = pd.to_datetime(df_orders['timestamp'], errors='coerce')
            today = pd.Timestamp.now().normalize()
            metrics['sales_today'] = df_orders[df_orders['dt'].dt.normalize() == today]['price'].sum()
            
        return metrics

    # --- EXPORTAR E IMPORTAR ---
    def get_database_as_bytes(self):
        with open(self.file, "rb") as f:
            return f.read()

    def import_database(self, uploaded_file):
        """Valida e importa un archivo Excel subido, reemplazando la base actual."""
        try:
            # Validación simple de que el archivo contiene hojas requeridas
            xls = pd.read_excel(uploaded_file, sheet_name=None)
            required_sheets = ['inventory', 'orders']
            
            for req in required_sheets:
                if req not in xls:
                    return False, f"Falta la hoja '{req}' en el archivo Excel."
                    
            with self.lock:
                with pd.ExcelWriter(self.file, engine='openpyxl') as writer:
                    for sheet_name, df in xls.items():
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
            return True, "Base de datos restaurada correctamente."
        except Exception as e:
            return False, str(e)
