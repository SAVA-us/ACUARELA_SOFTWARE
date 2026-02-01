import pandas as pd
import uuid
from datetime import datetime
import os
import hashlib
import io
import glob

# Constantes de referencia (se sobrescribirán dinámicamente si encontramos los archivos largos)
DEFAULT_INVENTORY = 'inventory.csv'
DEFAULT_ORDERS = 'orders.csv'
DEFAULT_ITEMS = 'orders_items.csv'
DEFAULT_SUPPLIERS = 'suppliers.csv'
USERS_FILE = 'users.csv'

class DataManager:
    def __init__(self):
        # Detectar automáticamente los archivos subidos
        self.files = {
            'inventory': self.find_file('inventory', DEFAULT_INVENTORY),
            'orders': self.find_file('orders.csv', DEFAULT_ORDERS), # .csv para distinguir de items
            'items': self.find_file('items', DEFAULT_ITEMS),
            'suppliers': self.find_file('suppliers', DEFAULT_SUPPLIERS)
        }
        self.ensure_files_exist()

    def find_file(self, keyword, default):
        """Busca un archivo que contenga la palabra clave en el directorio actual."""
        if os.path.exists(default):
            return default
            
        files = [f for f in os.listdir('.') if keyword in f and f.endswith('.csv')]
        
        # Caso especial para 'orders.csv'
        if keyword == 'orders.csv':
             files = [f for f in os.listdir('.') if 'orders' in f and 'items' not in f and f.endswith('.csv')]

        if files:
            return files[0]
        return default

    def ensure_files_exist(self):
        """Si no se encontraron archivos, crea los defaults vacíos"""
        
        if not os.path.exists(self.files['inventory']):
            pd.DataFrame(columns=[
                'id', 'name', 'purchase_price', 'updated_at', 'min_stock_alert', 
                'supplier_id', 'sale_price', 'quantity', 'supplier_name'
            ]).to_csv(self.files['inventory'], index=False)

        if not os.path.exists(self.files['orders']):
            pd.DataFrame(columns=[
                'id', 'timestamp', 'title', 'price', 'payment_method', 
                'customer_name', 'status', 'completed_at'
            ]).to_csv(self.files['orders'], index=False)

        if not os.path.exists(self.files['items']):
            pd.DataFrame(columns=[
                'order_id', 'order_date', 'item_name', 'quantity', 
                'sale_price', 'purchase_price', 'subtotal'
            ]).to_csv(self.files['items'], index=False)

        if not os.path.exists(self.files['suppliers']):
            pd.DataFrame(columns=['id', 'name', 'phone', 'email', 'contact_person']).to_csv(self.files['suppliers'], index=False)

        if not os.path.exists(USERS_FILE):
            default_pass = hashlib.sha256("admin123".encode()).hexdigest()
            pd.DataFrame({
                'username': ['admin'],
                'password': [default_pass],
                'role': ['admin'],
                'name': ['Administrador Principal']
            }).to_csv(USERS_FILE, index=False)

    # --- FUNCIONES DE EXCEL (LAS QUE FALTABAN) ---

    def get_database_as_excel(self):
        """Genera un archivo Excel binario con todas las tablas en hojas separadas"""
        output = io.BytesIO()
        # Usamos xlsxwriter como motor
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        
        # Leer dataframes actuales con manejo de errores
        try: df_inv = pd.read_csv(self.files['inventory'])
        except: df_inv = pd.DataFrame()
        
        try: df_ord = pd.read_csv(self.files['orders'])
        except: df_ord = pd.DataFrame()
        
        try: df_items = pd.read_csv(self.files['items'])
        except: df_items = pd.DataFrame()
        
        try: df_supp = pd.read_csv(self.files['suppliers'])
        except: df_supp = pd.DataFrame()
        
        # Escribir en hojas (Secciones Requeridas)
        df_inv.to_excel(writer, sheet_name='Inventario', index=False)
        df_ord.to_excel(writer, sheet_name='Ventas', index=False)
        df_items.to_excel(writer, sheet_name='Detalle_Ventas', index=False)
        df_supp.to_excel(writer, sheet_name='Proveedores', index=False)
        
        writer.close()
        processed_data = output.getvalue()
        return processed_data

    def import_database_from_excel(self, uploaded_file):
        """Lee un Excel y sobrescribe los CSVs del sistema"""
        try:
            # Leer todas las hojas
            xls = pd.read_excel(uploaded_file, sheet_name=None)
            
            # Mapeo flexible de nombres de hojas
            sheet_map = {
                'inventario': self.files['inventory'],
                'ventas': self.files['orders'],
                'orders': self.files['orders'],
                'detalle': self.files['items'],
                'items': self.files['items'],
                'proveedores': self.files['suppliers'],
                'suppliers': self.files['suppliers']
            }
            
            imported_count = 0
            for sheet_name, df in xls.items():
                # Normalizar nombre de hoja (quitar espacios, minúsculas)
                norm_name = sheet_name.lower().strip()
                
                # Buscar archivo destino
                target_file = None
                for key, val in sheet_map.items():
                    if key in norm_name:
                        target_file = val
                        break
                
                if target_file:
                    df.to_csv(target_file, index=False)
                    imported_count += 1
            
            return True, f"Se actualizaron {imported_count} secciones correctamente."
        except Exception as e:
            return False, str(e)

    # --- AUTENTICACIÓN ---
    def verify_user(self, username, password):
        try:
            df = pd.read_csv(USERS_FILE)
            hashed_pw = hashlib.sha256(password.encode()).hexdigest()
            user = df[(df['username'] == username) & (df['password'] == hashed_pw)]
            if not user.empty:
                return user.iloc[0].to_dict()
            return None
        except Exception:
            return None

    # --- MÉTODOS ESTÁNDAR ---
    def get_inventory(self):
        try: return pd.read_csv(self.files['inventory'])
        except: return pd.DataFrame()

    def add_product(self, product_data):
        df = pd.read_csv(self.files['inventory'])
        new_row = pd.DataFrame([product_data])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(self.files['inventory'], index=False)

    def register_sale(self, cart_items, total_price, payment_method="efectivo", customer_name="Cliente General"):
        order_id = str(uuid.uuid4())[:20]
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Crear registro en ORDERS
        new_order = {
            'id': order_id, 'timestamp': timestamp_str, 'title': f"Venta #{int(timestamp.timestamp())}",
            'price': total_price, 'payment_method': payment_method, 'customer_name': customer_name,
            'status': 'completed', 'completed_at': timestamp_str
        }
        
        df_orders = pd.read_csv(self.files['orders'])
        df_orders = pd.concat([df_orders, pd.DataFrame([new_order])], ignore_index=True)
        df_orders.to_csv(self.files['orders'], index=False)

        # 2. Items y 3. Actualizar Inventario
        df_items = pd.read_csv(self.files['items'])
        df_inventory = pd.read_csv(self.files['inventory'])
        
        items_to_add = []
        for item in cart_items:
            items_to_add.append({
                'order_id': order_id, 'order_date': timestamp_str, 'item_name': item['name'],
                'quantity': item['qty'], 'sale_price': item['sale_price'], 
                'purchase_price': item.get('purchase_price', 0), 'subtotal': item['sale_price'] * item['qty']
            })
            # Actualizar Stock
            mask = df_inventory['id'].astype(str) == str(item['id'])
            if mask.any():
                current_stock = df_inventory.loc[mask, 'quantity'].values[0]
                df_inventory.loc[mask, 'quantity'] = max(0, current_stock - item['qty'])

        if items_to_add:
            df_items = pd.concat([df_items, pd.DataFrame(items_to_add)], ignore_index=True)
            df_items.to_csv(self.files['items'], index=False)
            df_inventory.to_csv(self.files['inventory'], index=False)
            return True
        return False

    def get_sales_history(self):
        try: return pd.read_csv(self.files['orders'])
        except: return pd.DataFrame()
            
    def get_dashboard_metrics(self):
        try:
            df_inv = pd.read_csv(self.files['inventory'])
            df_orders = pd.read_csv(self.files['orders'])
            
            total_products = len(df_inv)
            total_inventory_value = (df_inv['quantity'] * df_inv['sale_price']).sum()
            low_stock_count = len(df_inv[df_inv['quantity'] <= df_inv['min_stock_alert']])
            
            df_orders['dt'] = pd.to_datetime(df_orders['timestamp'], errors='coerce')
            today = pd.Timestamp.now().normalize()
            sales_today = df_orders[df_orders['dt'].dt.normalize() == today]['price'].sum()
            
            return {
                "total_products": total_products, "inventory_value": total_inventory_value,
                "low_stock": low_stock_count, "sales_today": sales_today
            }
        except:
            return {"total_products": 0, "inventory_value": 0, "low_stock": 0, "sales_today": 0}
