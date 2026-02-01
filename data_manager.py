import pandas as pd
import uuid
from datetime import datetime
import os
import hashlib
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
        # Primero busca coincidencia exacta
        if os.path.exists(default):
            return default
            
        # Busca archivos que contengan la palabra clave (ej: 'SAVA...inventory.csv')
        files = [f for f in os.listdir('.') if keyword in f and f.endswith('.csv')]
        
        # Caso especial para 'orders.csv' para que no coincida con 'orders_items.csv'
        if keyword == 'orders.csv':
             files = [f for f in os.listdir('.') if 'orders' in f and 'items' not in f and f.endswith('.csv')]

        if files:
            # Devuelve el más reciente o el primero encontrado
            return files[0]
        return default

    def ensure_files_exist(self):
        """Si no se encontraron archivos, crea los defaults vacíos"""
        
        # 1. INVENTARIO
        if not os.path.exists(self.files['inventory']):
            df_inv = pd.DataFrame(columns=[
                'id', 'name', 'purchase_price', 'updated_at', 'min_stock_alert', 
                'supplier_id', 'sale_price', 'quantity', 'supplier_name'
            ])
            df_inv.to_csv(self.files['inventory'], index=False)

        # 2. PEDIDOS / VENTAS
        if not os.path.exists(self.files['orders']):
            df_orders = pd.DataFrame(columns=[
                'id', 'timestamp', 'title', 'price', 'payment_method', 
                'customer_name', 'status', 'completed_at'
            ])
            df_orders.to_csv(self.files['orders'], index=False)

        # 3. ITEMS DE PEDIDOS
        if not os.path.exists(self.files['items']):
            df_items = pd.DataFrame(columns=[
                'order_id', 'order_date', 'item_name', 'quantity', 
                'sale_price', 'purchase_price', 'subtotal'
            ])
            df_items.to_csv(self.files['items'], index=False)

        # 4. PROVEEDORES
        if not os.path.exists(self.files['suppliers']):
            df_supp = pd.DataFrame(columns=['id', 'name', 'phone', 'email', 'contact_person'])
            df_supp.to_csv(self.files['suppliers'], index=False)

        # 5. USUARIOS
        if not os.path.exists(USERS_FILE):
            default_pass = hashlib.sha256("admin123".encode()).hexdigest()
            df_users = pd.DataFrame({
                'username': ['admin'],
                'password': [default_pass],
                'role': ['admin'],
                'name': ['Administrador Principal']
            })
            df_users.to_csv(USERS_FILE, index=False)

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

    # --- INVENTARIO ---
    def get_inventory(self):
        try:
            return pd.read_csv(self.files['inventory'])
        except Exception as e:
            print(f"Error reading inventory: {e}")
            return pd.DataFrame()

    def add_product(self, product_data):
        df = pd.read_csv(self.files['inventory'])
        new_row = pd.DataFrame([product_data])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(self.files['inventory'], index=False)

    # --- VENTAS ---
    def register_sale(self, cart_items, total_price, payment_method="efectivo", customer_name="Cliente General"):
        order_id = str(uuid.uuid4())[:20]
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Crear registro en ORDERS
        new_order = {
            'id': order_id,
            'timestamp': timestamp_str,
            'title': f"Venta #{int(datetime.now().timestamp())}",
            'price': total_price,
            'payment_method': payment_method,
            'customer_name': customer_name,
            'status': 'completed',
            'completed_at': timestamp_str
        }
        
        df_orders = pd.read_csv(self.files['orders'])
        df_orders = pd.concat([df_orders, pd.DataFrame([new_order])], ignore_index=True)
        df_orders.to_csv(self.files['orders'], index=False)

        # 2. Items y 3. Actualizar Inventario
        df_items = pd.read_csv(self.files['items'])
        df_inventory = pd.read_csv(self.files['inventory'])
        
        items_to_add = []
        
        for item in cart_items:
            item_data = {
                'order_id': order_id,
                'order_date': timestamp_str,
                'item_name': item['name'],
                'quantity': item['qty'],
                'sale_price': item['sale_price'],
                'purchase_price': item.get('purchase_price', 0),
                'subtotal': item['sale_price'] * item['qty']
            }
            items_to_add.append(item_data)

            # Actualizar Stock
            # Intentar coincidencia exacta de ID (str vs str)
            mask = df_inventory['id'].astype(str) == str(item['id'])
            if mask.any():
                current_stock = df_inventory.loc[mask, 'quantity'].values[0]
                new_stock = max(0, current_stock - item['qty'])
                df_inventory.loc[mask, 'quantity'] = new_stock

        if items_to_add:
            df_items = pd.concat([df_items, pd.DataFrame(items_to_add)], ignore_index=True)
            df_items.to_csv(self.files['items'], index=False)
            df_inventory.to_csv(self.files['inventory'], index=False)
            return True
            
        return False

    def get_sales_history(self):
        try:
            return pd.read_csv(self.files['orders'])
        except Exception:
            return pd.DataFrame()
            
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
                "total_products": total_products,
                "inventory_value": total_inventory_value,
                "low_stock": low_stock_count,
                "sales_today": sales_today
            }
        except Exception:
            return {"total_products": 0, "inventory_value": 0, "low_stock": 0, "sales_today": 0}
