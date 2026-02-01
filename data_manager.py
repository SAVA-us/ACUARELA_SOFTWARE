import pandas as pd
import logging
import os
from datetime import datetime
from typing import Optional, Dict, List, Union, Tuple
from pathlib import Path

# --- Configuración de Logging ---
# Registra eventos importantes y errores en un archivo y en la consola
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s] - %(message)s',
    handlers=[
        logging.FileHandler("system.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("DataManager")

class AdvancedDataManager:
    """
    Gestor de datos de nivel empresarial.
    Maneja la persistencia, validación y sanitización del inventario.
    """

    # Definición de tipos esperados para garantizar la integridad de los datos
    COLUMN_TYPES = {
        'id': str,              # IDs como texto para preservar ceros a la izquierda (ej: "00123")
        'name': str,
        'quantity': int,        # Cantidades enteras (cambiar a float si vendes a granel)
        'purchase_price': float,
        'sale_price': float,
        'supplier_name': str,
        'min_stock_alert': int
    }

    def __init__(self, data_folder: str = "."):
        self.base_path = Path(data_folder)
        # Nombre exacto de tu archivo principal subido
        self.inventory_file = self.base_path / "Base de datos Acuarela.xlsx - Sheet1.csv"
        
        self._ensure_files_exist()

    def _ensure_files_exist(self):
        """Verifica la existencia de archivos críticos."""
        if not self.inventory_file.exists():
            logger.warning(f"Archivo principal no encontrado: {self.inventory_file}. Se creará uno nuevo al guardar.")

    def load_inventory(self) -> pd.DataFrame:
        """
        Lee el CSV con manejo estricto de tipos para evitar corrupción de datos.
        """
        if not self.inventory_file.exists():
            return pd.DataFrame(columns=self.COLUMN_TYPES.keys())

        try:
            # 1. Lectura optimizada
            df = pd.read_csv(
                self.inventory_file,
                dtype={'id': str}, # Crítico: fuerza la columna ID a texto
                keep_default_na=False,
                na_values=['', 'nan', 'NaN', 'N/A']
            )

            # 2. Normalización de cabeceras (elimina espacios y pone minúsculas)
            df.columns = [c.strip().lower() for c in df.columns]

            # 3. Validación y Limpieza
            df = self._sanitize_data(df)
            
            logger.info(f"Inventario cargado: {len(df)} productos activos.")
            return df

        except Exception as e:
            logger.error(f"Error crítico cargando inventario: {e}", exc_info=True)
            return pd.DataFrame(columns=self.COLUMN_TYPES.keys())

    def _sanitize_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Limpieza profunda de datos (Deep Cleaning)."""
        
        # Limpieza de IDs: string, sin decimales (.0), sin espacios
        if 'id' in df.columns:
            df['id'] = df['id'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
            # Eliminar IDs inválidos
            df = df[df['id'] != 'nan']
            df = df[df['id'].str.len() > 0]
            # Eliminar duplicados (mantiene el último modificado)
            df = df.drop_duplicates(subset=['id'], keep='last')

        # Limpieza de Nombres
        if 'name' in df.columns:
            df['name'] = df['name'].fillna("Sin Nombre").astype(str).str.title().str.strip()

        # Limpieza Numérica (Precios y Stock)
        numeric_cols = ['quantity', 'purchase_price', 'sale_price', 'min_stock_alert']
        for col in numeric_cols:
            if col in df.columns:
                # Coerce convierte errores (texto) en NaN, luego fillna pone 0
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                # Asegurar valores positivos en precios
                if 'price' in col:
                    df[col] = df[col].abs()
        
        # Conversión final de tipos
        if 'quantity' in df.columns:
            df['quantity'] = df['quantity'].astype(int)

        return df

    def save_inventory(self, df: pd.DataFrame) -> bool:
        """Guarda el estado actual del inventario."""
        try:
            # Añadir timestamp de actualización
            df['updated_at'] = datetime.now().isoformat()
            df.to_csv(self.inventory_file, index=False)
            logger.info("Inventario guardado exitosamente.")
            return True
        except Exception as e:
            logger.error(f"Error guardando inventario: {e}")
            return False

    def update_stock(self, product_id: str, delta: int) -> Tuple[bool, str]:
        """
        Actualiza el stock de forma transaccional.
        delta: negativo para ventas, positivo para reposición.
        """
        df = self.load_inventory()
        product_id = str(product_id).strip()
        
        mask = df['id'] == product_id
        if not mask.any():
            return False, "Producto no encontrado."

        current_qty = df.loc[mask, 'quantity'].values[0]
        new_qty = current_qty + delta

        # Validación de stock negativo
        if new_qty < 0:
            return False, f"Stock insuficiente (Disponible: {current_qty})"

        df.loc[mask, 'quantity'] = int(new_qty)
        
        if self.save_inventory(df):
            return True, f"Stock actualizado. Nuevo saldo: {new_qty}"
        return False, "Error de escritura en disco."
