import pandas as pd
import os
import datetime

# Nombres de archivos mapeados a tus CSVs exportados
FILE_INVENTORY = "Base de datos Acuarela.xlsx - Sheet1.csv"
FILE_ORDERS = "Base de datos Acuarela.xlsx - orders.csv"
FILE_SUPPLIERS = "Base de datos Acuarela.xlsx - suppliers.csv"

class DataManager:
    def __init__(self):
        """Inicializa el gestor de datos cargando los CSVs locales."""
        self.inventory_df = pd.DataFrame()
        self.orders_df = pd.DataFrame()
        self.suppliers_df = pd.DataFrame()
        self.load_data()

    def load_data(self):
        """Carga y limpia los datos desde los archivos CSV."""
        try:
            # 1. Cargar Inventario
            if os.path.exists(FILE_INVENTORY):
                self.inventory_df = pd.read_csv(FILE_INVENTORY)
                # Limpieza crítica: Convertir columnas numéricas que vienen como texto
                cols_to_numeric = ['sale_price', 'purchase_price', 'quantity', 'min_stock_alert']
                for col in cols_to_numeric:
                    if col in self.inventory_df.columns:
                        self.inventory_df[col] = pd.to_numeric(self.inventory_df[col], errors='coerce').fillna(0)
                
                # Asegurar que el ID sea string para búsquedas
                if 'id' in self.inventory_df.columns:
                    self.inventory_df['id'] = self.inventory_df['id'].astype(str)
            else:
                self.inventory_df = pd.DataFrame(columns=['id', 'name', 'quantity', 'sale_price', 'purchase_price'])

            # 2. Cargar Pedidos
            if os.path.exists(FILE_ORDERS):
                self.orders_df = pd.read_csv(FILE_ORDERS)
            
            print("✅ Datos cargados correctamente desde CSV local.")
            
        except Exception as e:
            print(f"❌ Error cargando datos: {e}")

    # --- Métodos de Lectura (Reemplazan a Firebase.get) ---
    def get_all_products(self):
        return self.inventory_df.to_dict('records')

    def get_product_by_barcode(self, barcode):
        """Busca producto por ID o Código de Barras"""
        if self.inventory_df.empty: return None
        
        # Buscar coincidencia exacta en ID
        prod = self.inventory_df[self.inventory_df['id'] == str(barcode)]
        if not prod.empty:
            return prod.iloc[0].to_dict()
        return None

    def get_low_stock_products(self):
        """Filtra productos con stock bajo"""
        if self.inventory_df.empty: return []
        return self.inventory_df[self.inventory_df['quantity'] <= self.inventory_df['min_stock_alert']].to_dict('records')

    # --- Métodos de Escritura (Reemplazan a Firebase.update/set) ---
    def update_stock(self, product_id, quantity_change):
        """Actualiza el stock en memoria (y teóricamente guarda en CSV)"""
        idx = self.inventory_df.index[self.inventory_df['id'] == str(product_id)].tolist()
        if idx:
            current_qty = self.inventory_df.at[idx[0], 'quantity']
            new_qty = max(0, current_qty + quantity_change) # No permitir stock negativo
            self.inventory_df.at[idx[0], 'quantity'] = new_qty
            return True
        return False

    def record_sale(self, cart_items, total, payment_method):
        """Registra una venta en el historial"""
        new_order = {
            "id": f"ORD-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
            "timestamp": datetime.datetime.now().isoformat(),
            "total": total,
            "items_count": len(cart_items),
            "payment_method": payment_method,
            "status": "completed"
        }
        # Agregar al DataFrame de ordenes
        self.orders_df = pd.concat([self.orders_df, pd.DataFrame([new_order])], ignore_index=True)
        return new_order['id']

    def calculate_metrics(self):
        """Calcula KPIs financieros"""
        total_inv_value = (self.inventory_df['quantity'] * self.inventory_df['sale_price']).sum()
        total_inv_cost = (self.inventory_df['quantity'] * self.inventory_df['purchase_price']).sum()
        return {
            "total_value": total_inv_value,
            "total_cost": total_inv_cost,
            "potential_profit": total_inv_value - total_inv_cost,
            "product_count": len(self.inventory_df)
        }
