import pandas as pd
import os
import datetime

# Constantes de Archivos (Mapeados a tus subidas)
FILE_INVENTORY = "Base de datos Acuarela.xlsx - Sheet1.csv"
FILE_ORDERS = "Base de datos Acuarela.xlsx - orders.csv"
FILE_ORDER_ITEMS = "Base de datos Acuarela.xlsx - orders_items.csv"
FILE_SUPPLIERS = "Base de datos Acuarela.xlsx - suppliers.csv"

class DataManager:
    def __init__(self, use_google_sheets=False):
        """
        Inicializa el gestor de datos.
        :param use_google_sheets: Si es True, intenta conectar a GSheets (requiere credenciales).
                                  Si es False, usa los CSVs locales.
        """
        self.use_google_sheets = use_google_sheets
        self.inventory_df = pd.DataFrame()
        self.orders_df = pd.DataFrame()
        self.suppliers_df = pd.DataFrame()
        self.load_data()

    def load_data(self):
        """Carga datos desde CSV (o GSheets en el futuro) y limpia tipos de datos."""
        try:
            # 1. Cargar Inventario
            if os.path.exists(FILE_INVENTORY):
                self.inventory_df = pd.read_csv(FILE_INVENTORY)
                # Limpieza de datos: Asegurar que precios y cantidades sean numéricos
                self.inventory_df['sale_price'] = pd.to_numeric(self.inventory_df['sale_price'], errors='coerce').fillna(0)
                self.inventory_df['purchase_price'] = pd.to_numeric(self.inventory_df['purchase_price'], errors='coerce').fillna(0)
                self.inventory_df['quantity'] = pd.to_numeric(self.inventory_df['quantity'], errors='coerce').fillna(0)
                # Convertir ID a string para búsquedas consistentes
                self.inventory_df['id'] = self.inventory_df['id'].astype(str)
            else:
                self.inventory_df = pd.DataFrame(columns=['id', 'name', 'quantity', 'sale_price', 'purchase_price', 'supplier_name', 'min_stock_alert'])

            # 2. Cargar Pedidos
            if os.path.exists(FILE_ORDERS):
                self.orders_df = pd.read_csv(FILE_ORDERS)
            else:
                self.orders_df = pd.DataFrame(columns=['id', 'timestamp', 'total', 'status', 'payment_method'])

            # 3. Cargar Proveedores
            if os.path.exists(FILE_SUPPLIERS):
                self.suppliers_df = pd.read_csv(FILE_SUPPLIERS)
            else:
                self.suppliers_df = pd.DataFrame(columns=['id', 'name', 'contact_person', 'phone'])
            
            print("Datos cargados correctamente.")
            
        except Exception as e:
            print(f"Error cargando datos: {e}")

    def get_inventory(self):
        return self.inventory_df

    def get_low_stock_items(self):
        """Retorna items donde la cantidad es menor o igual a la alerta de stock mínimo."""
        if self.inventory_df.empty:
            return pd.DataFrame()
        
        # Asegurar comparación numérica
        mask = self.inventory_df['quantity'] <= self.inventory_df['min_stock_alert']
        return self.inventory_df[mask]

    def get_product_by_barcode(self, barcode):
        """Busca un producto por su código de barras (id)."""
        if self.inventory_df.empty:
            return None
        
        product = self.inventory_df[self.inventory_df['id'] == str(barcode)]
        if not product.empty:
            return product.iloc[0].to_dict()
        return None

    def update_product_stock(self, barcode, new_quantity):
        """Actualiza el stock de un producto (Simulado en memoria/CSV)."""
        idx = self.inventory_df.index[self.inventory_df['id'] == str(barcode)].tolist()
        if idx:
            self.inventory_df.at[idx[0], 'quantity'] = new_quantity
            # En un entorno real, aquí guardaríamos de vuelta al CSV o Google Sheet
            # self.save_inventory()
            return True
        return False
    
    def calculate_kpis(self):
        """Calcula métricas clave para el dashboard."""
        total_products = len(self.inventory_df)
        
        # Valor del inventario (Costo vs Venta)
        total_cost_value = (self.inventory_df['quantity'] * self.inventory_df['purchase_price']).sum()
        total_sales_value = (self.inventory_df['quantity'] * self.inventory_df['sale_price']).sum()
        potential_profit = total_sales_value - total_cost_value
        
        low_stock_count = len(self.get_low_stock_items())
        
        return {
            "total_products": total_products,
            "inventory_cost": total_cost_value,
            "inventory_value": total_sales_value,
            "potential_profit": potential_profit,
            "low_stock": low_stock_count
        }

    # --- Placeholder para futura implementación de Google Sheets ---
    def sync_to_google_sheets(self):
        """
        Para activar esto en el futuro:
        1. Configurar gspread con credenciales.json.
        2. Abrir la hoja por nombre.
        3. Usar set_with_dataframe de gspread-dataframe.
        """
        pass
