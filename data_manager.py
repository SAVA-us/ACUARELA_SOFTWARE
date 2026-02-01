import pandas as pd
import uuid
from datetime import datetime
import os
import hashlib
import io

# Nombres de archivos internos (el sistema usa CSV para velocidad, pero importará/exportará Excel)
DEFAULT_INVENTORY = 'inventory.csv'
DEFAULT_ORDERS = 'orders.csv'
DEFAULT_ITEMS = 'orders_items.csv'
DEFAULT_SUPPLIERS = 'suppliers.csv'
USERS_FILE = 'users.csv'

class DataManager:
    def __init__(self):
        # Mapeo de archivos
        self.files = {
            'inventory': self.find_file('inventory', DEFAULT_INVENTORY),
            'orders': self.find_file('orders.csv', DEFAULT_ORDERS),
            'items': self.find_file('items', DEFAULT_ITEMS),
            'suppliers': self.find_file('suppliers', DEFAULT_SUPPLIERS),
            'users': USERS_FILE
        }
        self.ensure_files_exist()

    def find_file(self, keyword, default):
        """Busca archivos de forma inteligente"""
        if os.path.exists(default): return default
        # Buscar CSVs que coincidan
        files = [f for f in os.listdir('.') if keyword in f and f.endswith('.csv')]
        if keyword == 'orders.csv': # Evitar conflicto con orders_items
             files = [f for f in os.listdir('.') if 'orders' in f and 'items' not in f and f.endswith('.csv')]
        return files[0] if files else default

    def ensure_files_exist(self):
        """Inicializa archivos si no existen"""
        if not os.path.exists(self.files['inventory']):
            pd.DataFrame(columns=['id', 'name', 'purchase_price', 'sale_price', 'quantity', 'supplier_name', 'min_stock_alert', 'updated_at']).to_csv(self.files['inventory'], index=False)
        if not os.path.exists(self.files['orders']):
            pd.DataFrame(columns=['id', 'timestamp', 'price', 'payment_method', 'status']).to_csv(self.files['orders'], index=False)
        if not os.path.exists(self.files['items']):
            pd.DataFrame(columns=['order_id', 'item_name', 'quantity', 'sale_price', 'subtotal']).to_csv(self.files['items'], index=False)
        if not os.path.exists(self.files['suppliers']):
            pd.DataFrame(columns=['id', 'name', 'phone']).to_csv(self.files['suppliers'], index=False)
        if not os.path.exists(USERS_FILE):
            # Admin por defecto
            pd.DataFrame({'username': ['admin'], 'password': [hashlib.sha256("admin123".encode()).hexdigest()], 'name': ['Admin']}).to_csv(USERS_FILE, index=False)

    # --- FUNCIONES EXCEL (NUEVO) ---
    
    def get_database_as_excel(self):
        """Genera un archivo Excel binario con todas las tablas en hojas separadas"""
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        
        # Leer dataframes actuales
        df_inv = self.get_inventory()
        df_ord = self.get_sales_history()
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
            
            # Mapeo de nombres de hojas a archivos internos
            # Intentamos ser flexibles con los nombres de las hojas
            sheet_map = {
                'Inventario': self.files['inventory'],
                'inventory': self.files['inventory'],
                'Ventas': self.files['orders'],
                'orders': self.files['orders'],
                'Detalle_Ventas': self.files['items'],
                'orders_items': self.files['items'],
                'Proveedores': self.files['suppliers'],
                'suppliers': self.files['suppliers']
            }
            
            imported_count = 0
            for sheet_name, df in xls.items():
                # Normalizar nombre de hoja (quitar espacios, minúsculas)
                norm_name = sheet_name.strip()
                target_file = None
                
                # Buscar coincidencia
                for key, val in sheet_map.items():
                    if key.lower() in norm_name.lower():
                        target_file = val
                        break
                
                if target_file:
                    df.to_csv(target_file, index=False)
                    imported_count += 1
            
            return True, f"Se actualizaron {imported_count} secciones correctamente."
        except Exception as e:
            return False, str(e)

    # --- MÉTODOS EXISTENTES (Simplificados para brevedad, lógica intacta) ---
    def verify_user(self, u, p):
        try:
            df = pd.read_csv(USERS_FILE)
            if not df[(df['username']==u) & (df['password']==hashlib.sha256(p.encode()).hexdigest())].empty:
                return df[df['username']==u].iloc[0].to_dict()
        except: pass
        return None

    def get_inventory(self):
        try: return pd.read_csv(self.files['inventory'])
        except: return pd.DataFrame()

    def add_product(self, data):
        df = self.get_inventory()
        df = pd.concat([df, pd.DataFrame([data])], ignore_index=True)
        df.to_csv(self.files['inventory'], index=False)

    def register_sale(self, cart, total, method, customer="Cliente General"):
        order_id = str(uuid.uuid4())[:20]
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Guardar Orden
        new_order = {'id': order_id, 'timestamp': ts, 'price': total, 'payment_method': method, 'customer_name': customer, 'status': 'completed'}
        df_ord = pd.read_csv(self.files['orders'])
        df_ord = pd.concat([df_ord, pd.DataFrame([new_order])], ignore_index=True)
        df_ord.to_csv(self.files['orders'], index=False)
        
        # Guardar Items y Actualizar Stock
        df_items = pd.read_csv(self.files['items'])
        df_inv = pd.read_csv(self.files['inventory'])
        new_items = []
        
        for item in cart:
            new_items.append({
                'order_id': order_id, 'order_date': ts, 'item_name': item['name'], 
                'quantity': item['qty'], 'sale_price': item['sale_price'], 'subtotal': item['qty']*item['sale_price']
            })
            # Restar stock
            mask = df_inv['id'].astype(str) == str(item['id'])
            if mask.any():
                df_inv.loc[mask, 'quantity'] = df_inv.loc[mask, 'quantity'] - item['qty']
        
        if new_items:
            df_items = pd.concat([df_items, pd.DataFrame(new_items)], ignore_index=True)
            df_items.to_csv(self.files['items'], index=False)
            df_inv.to_csv(self.files['inventory'], index=False)
            return True
        return False

    def get_sales_history(self):
        try: return pd.read_csv(self.files['orders'])
        except: return pd.DataFrame()

    def get_dashboard_metrics(self):
        try:
            df_inv = self.get_inventory()
            df_ord = self.get_sales_history()
            df_ord['dt'] = pd.to_datetime(df_ord['timestamp'], errors='coerce')
            today_sales = df_ord[df_ord['dt'].dt.normalize() == pd.Timestamp.now().normalize()]['price'].sum()
            return {
                "total_products": len(df_inv),
                "inventory_value": (df_inv['quantity'] * df_inv['sale_price']).sum(),
                "low_stock": len(df_inv[df_inv['quantity'] <= df_inv['min_stock_alert']]),
                "sales_today": today_sales
            }
        except: return {"total_products": 0, "inventory_value": 0, "low_stock": 0, "sales_today": 0}
