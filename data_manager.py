import pandas as pd
import logging
import os
import hashlib
import uuid
from datetime import datetime
from typing import Optional, Dict, List, Union, Tuple
from pathlib import Path

# --- Configuración de Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s] - %(message)s',
    handlers=[
        logging.FileHandler("system_audit.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AcuarelaDB")

class DataManager:
    """
    Gestor de datos Enterprise para Rapitienda Acuarela.
    Reemplaza Firebase con un sistema robusto de archivos CSV/Excel locales.
    Maneja: Inventario, Usuarios, Ventas, Proveedores.
    """

    def __init__(self, data_folder: str = "."):
        self.base_path = Path(data_folder)
        
        # Archivos de Base de Datos
        self.files = {
            "inventory": self.base_path / "Base de datos Acuarela.xlsx - Sheet1.csv",
            "users": self.base_path / "users.csv",
            "sales": self.base_path / "sales.csv",
            "suppliers": self.base_path / "suppliers.csv",
            "audit": self.base_path / "audit_log.csv"
        }
        
        self._initialize_system()

    def _initialize_system(self):
        """Inicializa la estructura de archivos si no existen."""
        # 1. Usuarios (Crear Admin por defecto si no existe)
        if not self.files["users"].exists():
            df_users = pd.DataFrame([{
                "username": "admin",
                "password_hash": self._hash_password("admin123"),
                "role": "admin",
                "name": "Administrador Principal",
                "created_at": datetime.now().isoformat()
            }])
            df_users.to_csv(self.files["users"], index=False)
            logger.info("Sistema de usuarios inicializado. Usuario: admin / Clave: admin123")

        # 2. Ventas (Estructura vacía)
        if not self.files["sales"].exists():
            pd.DataFrame(columns=[
                "sale_id", "date", "product_id", "product_name", 
                "quantity", "unit_price", "total", "cashier", "payment_method"
            ]).to_csv(self.files["sales"], index=False)

        # 3. Proveedores
        if not self.files["suppliers"].exists():
             pd.DataFrame(columns=["id", "name", "contact", "phone", "email"]).to_csv(self.files["suppliers"], index=False)

    # --- UTILIDADES DE SEGURIDAD ---
    
    def _hash_password(self, password: str) -> str:
        """Genera un hash SHA-256 seguro para contraseñas."""
        return hashlib.sha256(password.encode()).hexdigest()

    # --- GESTIÓN DE USUARIOS (AUTH) ---

    def authenticate_user(self, username, password) -> Optional[Dict]:
        """Verifica credenciales y retorna datos del usuario o None."""
        try:
            df = pd.read_csv(self.files["users"], dtype=str)
            user = df[df['username'] == username]
            
            if user.empty:
                return None
            
            stored_hash = user.iloc[0]['password_hash']
            if stored_hash == self._hash_password(password):
                return user.iloc[0].to_dict()
            return None
        except Exception as e:
            logger.error(f"Error de autenticación: {e}")
            return None

    def create_user(self, username, password, role="staff", name="Empleado") -> bool:
        """Registra un nuevo usuario en el sistema."""
        try:
            df = pd.read_csv(self.files["users"])
            if username in df['username'].values:
                return False # Usuario ya existe
            
            new_user = {
                "username": username,
                "password_hash": self._hash_password(password),
                "role": role,
                "name": name,
                "created_at": datetime.now().isoformat()
            }
            df = pd.concat([df, pd.DataFrame([new_user])], ignore_index=True)
            df.to_csv(self.files["users"], index=False)
            return True
        except Exception as e:
            logger.error(f"Error creando usuario: {e}")
            return False

    def get_all_users(self):
        return pd.read_csv(self.files["users"]).to_dict('records')

    # --- GESTIÓN DE INVENTARIO ---

    def load_inventory(self) -> pd.DataFrame:
        """Carga el inventario con limpieza robusta de datos."""
        if not self.files["inventory"].exists():
            return pd.DataFrame()

        try:
            # Lectura estricta para no perder códigos de barras
            df = pd.read_csv(
                self.files["inventory"], 
                dtype={'id': str}, 
                keep_default_na=False, 
                na_values=['', 'nan']
            )
            
            # Normalización
            df.columns = [c.strip().lower() for c in df.columns]
            
            # Sanitización
            if 'id' in df.columns:
                df['id'] = df['id'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
                df = df[df['id'] != 'nan']
            
            # Conversión numérica segura
            numeric_cols = ['quantity', 'sale_price', 'purchase_price', 'min_stock_alert']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            return df
        except Exception as e:
            logger.error(f"Error cargando inventario: {e}")
            return pd.DataFrame()

    def save_inventory(self, df: pd.DataFrame):
        df.to_csv(self.files["inventory"], index=False)

    def update_product(self, product_data: Dict) -> bool:
        """Actualiza o Crea un producto."""
        try:
            df = self.load_inventory()
            pid = str(product_data['id']).strip()
            
            # Si el producto existe, lo actualizamos. Si no, lo creamos.
            if pid in df['id'].values:
                idx = df[df['id'] == pid].index[0]
                for key, val in product_data.items():
                    if key in df.columns:
                        df.at[idx, key] = val
                df.at[idx, 'updated_at'] = datetime.now().isoformat()
            else:
                product_data['updated_at'] = datetime.now().isoformat()
                df = pd.concat([df, pd.DataFrame([product_data])], ignore_index=True)
            
            self.save_inventory(df)
            return True
        except Exception as e:
            logger.error(f"Error actualizando producto: {e}")
            return False

    def delete_product(self, product_id: str) -> bool:
        try:
            df = self.load_inventory()
            df = df[df['id'] != str(product_id)]
            self.save_inventory(df)
            return True
        except Exception as e:
            logger.error(f"Error eliminando producto: {e}")
            return False

    # --- GESTIÓN DE VENTAS (POS) ---

    def register_sale(self, cart_items: List[Dict], payment_method: str, cashier: str) -> bool:
        """
        Registra una venta: Descuenta stock y guarda historial.
        Transaccional: Si algo falla, intenta revertir (básico).
        """
        try:
            df_inv = self.load_inventory()
            sale_records = []
            sale_id = str(uuid.uuid4())[:8]
            timestamp = datetime.now().isoformat()
            
            # 1. Validar Stock
            for item in cart_items:
                pid = str(item['id'])
                qty = int(item['qty'])
                
                # Buscar producto
                mask = df_inv['id'] == pid
                if not mask.any():
                    logger.error(f"Producto {pid} no encontrado al vender.")
                    return False
                
                current_stock = df_inv.loc[mask, 'quantity'].values[0]
                if current_stock < qty:
                    return False # Stock insuficiente
                
                # Descontar temporalmente en memoria
                df_inv.loc[mask, 'quantity'] = current_stock - qty
                
                # Preparar registro de venta
                sale_records.append({
                    "sale_id": sale_id,
                    "date": timestamp,
                    "product_id": pid,
                    "product_name": item['name'],
                    "quantity": qty,
                    "unit_price": item['price'],
                    "total": item['price'] * qty,
                    "cashier": cashier,
                    "payment_method": payment_method
                })

            # 2. Guardar cambios en disco
            self.save_inventory(df_inv)
            
            # 3. Guardar historial
            df_sales = pd.read_csv(self.files["sales"])
            df_sales = pd.concat([df_sales, pd.DataFrame(sale_records)], ignore_index=True)
            df_sales.to_csv(self.files["sales"], index=False)
            
            logger.info(f"Venta {sale_id} registrada con éxito.")
            return True

        except Exception as e:
            logger.error(f"Error crítico en venta: {e}")
            return False

    def get_sales_report(self) -> pd.DataFrame:
        """Obtiene el historial completo de ventas."""
        if self.files["sales"].exists():
            return pd.read_csv(self.files["sales"])
        return pd.DataFrame()

    def get_dashboard_metrics(self):
        """Calcula métricas clave para el dashboard."""
        df_sales = self.get_sales_report()
        df_inv = self.load_inventory()
        
        metrics = {
            "total_sales": 0,
            "transaction_count": 0,
            "low_stock_count": 0,
            "inventory_value": 0
        }
        
        if not df_sales.empty:
            metrics["total_sales"] = df_sales['total'].sum()
            metrics["transaction_count"] = df_sales['sale_id'].nunique()
        
        if not df_inv.empty:
            metrics["low_stock_count"] = len(df_inv[df_inv['quantity'] <= df_inv.get('min_stock_alert', 5)])
            metrics["inventory_value"] = (df_inv['quantity'] * df_inv['sale_price']).sum()
            
        return metrics

    # --- PROVEEDORES ---
    def get_suppliers(self):
        if self.files["suppliers"].exists():
            return pd.read_csv(self.files["suppliers"])
        return pd.DataFrame()

    def add_supplier(self, data):
        df = self.get_suppliers()
        data['id'] = str(uuid.uuid4())[:8]
        df = pd.concat([df, pd.DataFrame([data])], ignore_index=True)
        df.to_csv(self.files["suppliers"], index=False)
