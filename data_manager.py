import pandas as pd
import uuid
from datetime import datetime
import os
import hashlib

# Nombres de archivos basados en tus exportaciones
INVENTORY_FILE = 'inventory.csv'
ORDERS_FILE = 'orders.csv'
ORDERS_ITEMS_FILE = 'orders_items.csv'
SUPPLIERS_FILE = 'suppliers.csv'
USERS_FILE = 'users.csv'  # Archivo local para usuarios

class DataManager:
    def __init__(self):
        self.ensure_files_exist()

    def ensure_files_exist(self):
        """Crea los archivos CSV vacíos con las cabeceras correctas si no existen"""
        
        # 1. INVENTARIO (Estructura basada en tu Excel)
        if not os.path.exists(INVENTORY_FILE):
            df_inv = pd.DataFrame(columns=[
                'id', 'name', 'purchase_price', 'updated_at', 'min_stock_alert', 
                'supplier_id', 'sale_price', 'quantity', 'supplier_name'
            ])
            df_inv.to_csv(INVENTORY_FILE, index=False)

        # 2. PEDIDOS / VENTAS (Estructura basada en tu Excel)
        if not os.path.exists(ORDERS_FILE):
            df_orders = pd.DataFrame(columns=[
                'id', 'timestamp', 'title', 'price', 'payment_method', 
                'customer_name', 'status', 'completed_at'
            ])
            df_orders.to_csv(ORDERS_FILE, index=False)

        # 3. ITEMS DE PEDIDOS (Estructura basada en tu Excel)
        if not os.path.exists(ORDERS_ITEMS_FILE):
            df_items = pd.DataFrame(columns=[
                'order_id', 'order_date', 'item_name', 'quantity', 
                'sale_price', 'purchase_price', 'subtotal'
            ])
            df_items.to_csv(ORDERS_ITEMS_FILE, index=False)

        # 4. PROVEEDORES
        if not os.path.exists(SUPPLIERS_FILE):
            df_supp = pd.DataFrame(columns=['id', 'name', 'phone', 'email', 'contact_person'])
            df_supp.to_csv(SUPPLIERS_FILE, index=False)

        # 5. USUARIOS (Sistema local simple)
        if not os.path.exists(USERS_FILE):
            # Crear usuario admin por defecto
            # admin / admin123
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
            return pd.read_csv(INVENTORY_FILE)
        except Exception:
            return pd.DataFrame()

    def update_product(self, product_id, updates):
        """Actualiza un producto existente"""
        df = pd.read_csv(INVENTORY_FILE)
        if product_id in df['id'].values:
            for key, value in updates.items():
                if key in df.columns:
                    df.loc[df['id'] == product_id, key] = value
            
            # Actualizar timestamp
            df.loc[df['id'] == product_id, 'updated_at'] = datetime.now().isoformat()
            df.to_csv(INVENTORY_FILE, index=False)
            return True
        return False

    def add_product(self, product_data):
        df = pd.read_csv(INVENTORY_FILE)
        new_row = pd.DataFrame([product_data])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(INVENTORY_FILE, index=False)

    # --- VENTAS ---
    def register_sale(self, cart_items, total_price, payment_method="efectivo", customer_name="Cliente General"):
        """
        Registra una venta impactando:
        1. orders.csv (La cabecera de la venta)
        2. orders_items.csv (Los detalles de cada producto)
        3. inventory.csv (Resta el stock)
        """
        order_id = str(uuid.uuid4())[:20] # ID corto compatible con tus datos
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Crear registro en ORDERS
        new_order = {
            'id': order_id,
            'timestamp': timestamp_str,
            'title': f"Venta #{int(datetime.now().timestamp())}", # Simulación de num venta
            'price': total_price,
            'payment_method': payment_method,
            'customer_name': customer_name,
            'status': 'completed',
            'completed_at': timestamp_str
        }
        
        df_orders = pd.read_csv(ORDERS_FILE)
        df_orders = pd.concat([df_orders, pd.DataFrame([new_order])], ignore_index=True)
        df_orders.to_csv(ORDERS_FILE, index=False)

        # 2. Crear registros en ORDER ITEMS y 3. Actualizar INVENTARIO
        df_items = pd.read_csv(ORDERS_ITEMS_FILE)
        df_inventory = pd.read_csv(INVENTORY_FILE)
        
        items_to_add = []
        
        for item in cart_items:
            # Datos para orders_items.csv
            item_data = {
                'order_id': order_id,
                'order_date': timestamp_str,
                'item_name': item['name'],
                'quantity': item['qty'],
                'sale_price': item['sale_price'],
                'purchase_price': item.get('purchase_price', 0), # Fallback si no existe
                'subtotal': item['sale_price'] * item['qty']
            }
            items_to_add.append(item_data)

            # Actualizar Stock en inventory.csv
            # Buscamos por ID si existe, sino por nombre exacto
            mask = df_inventory['id'] == item['id']
            if mask.any():
                current_stock = df_inventory.loc[mask, 'quantity'].values[0]
                new_stock = max(0, current_stock - item['qty'])
                df_inventory.loc[mask, 'quantity'] = new_stock

        # Guardar cambios
        if items_to_add:
            df_items = pd.concat([df_items, pd.DataFrame(items_to_add)], ignore_index=True)
            df_items.to_csv(ORDERS_ITEMS_FILE, index=False)
            df_inventory.to_csv(INVENTORY_FILE, index=False)
            return True
            
        return False

    def get_sales_history(self):
        """Obtiene el historial uniendo orders con items si es necesario, 
           o simplemente devolviendo orders"""
        try:
            return pd.read_csv(ORDERS_FILE)
        except Exception:
            return pd.DataFrame()
            
    def get_dashboard_metrics(self):
        try:
            df_inv = pd.read_csv(INVENTORY_FILE)
            df_orders = pd.read_csv(ORDERS_FILE)
            
            # Calcular métricas
            total_products = len(df_inv)
            # Manejar posibles valores nulos en precios
            total_inventory_value = (df_inv['quantity'] * df_inv['sale_price']).sum()
            low_stock_count = len(df_inv[df_inv['quantity'] <= df_inv['min_stock_alert']])
            
            # Ventas de hoy (convertir string a fecha)
            df_orders['dt'] = pd.to_datetime(df_orders['timestamp'], errors='coerce')
            today = pd.Timestamp.now().normalize()
            sales_today = df_orders[df_orders['dt'].dt.normalize() == today]['price'].sum()
            
            return {
                "total_products": total_products,
                "inventory_value": total_inventory_value,
                "low_stock": low_stock_count,
                "sales_today": sales_today
            }
        except Exception as e:
            print(f"Error metrics: {e}")
            return {"total_products": 0, "inventory_value": 0, "low_stock": 0, "sales_today": 0}
