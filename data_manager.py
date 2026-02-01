import pandas as pd
import logging
import os
from datetime import datetime
from typing import Optional, Dict, List, Union, Tuple
from pathlib import Path

# Configuración de Logging Profesional
# Esto nos permite ver errores detallados y advertencias en la consola o guardar un archivo de log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

class AdvancedDataManager:
    """
    Gestor de datos avanzado para el manejo de inventarios y pedidos.
    Diseñado para ser robusto ante errores de formato en archivos Excel/CSV.
    """

    # Definición estricta de columnas esperadas y sus tipos
    REQUIRED_COLUMNS = {
        'id': str,              # El código de barras DEBE ser string para no perder ceros a la izquierda
        'name': str,
        'quantity': float,      # Float para permitir pesaje (kg) si fuera necesario, o int luego
        'purchase_price': float,
        'sale_price': float,
        'supplier_name': str,
        'min_stock_alert': float
    }

    def __init__(self, data_folder: str = "data"):
        """
        Inicializa el gestor de datos.
        :param data_folder: Carpeta donde se encuentran los archivos CSV/Excel.
        """
        self.base_path = Path(data_folder)
        self.inventory_file = self.base_path / "Base de datos Acuarela.xlsx - Sheet1.csv" # Apunta a tu archivo principal
        
        # Asegurar que el directorio existe
        if not self.base_path.exists():
            os.makedirs(self.base_path)
            logger.info(f"Directorio de datos creado: {self.base_path}")

    def load_inventory(self) -> pd.DataFrame:
        """
        Carga el inventario leyendo el archivo con máxima precisión.
        Realiza limpieza y validación de tipos.
        """
        if not self.inventory_file.exists():
            logger.warning(f"Archivo de inventario no encontrado en: {self.inventory_file}")
            return pd.DataFrame(columns=self.REQUIRED_COLUMNS.keys())

        try:
            logger.info(f"Iniciando lectura de inventario: {self.inventory_file}")
            
            # 1. LECTURA ROBUSTA
            # dtype={'id': str} es CRUCIAL. Evita que '00123' se convierta en 123
            df = pd.read_csv(
                self.inventory_file, 
                dtype={'id': str}, # Forzamos que el ID sea siempre texto
                keep_default_na=False, # Control manual de Nulos
                na_values=['', 'nan', 'NaN', '#N/A']
            )

            # 2. NORMALIZACIÓN DE COLUMNAS
            # Eliminamos espacios en los nombres de columnas y pasamos a minúsculas para evitar errores por " Name" vs "name"
            df.columns = [c.strip().lower() for c in df.columns]
            
            # Verificación de columnas críticas
            missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
            if missing_cols:
                logger.error(f"Faltan columnas críticas en el archivo: {missing_cols}")
                # Podríamos lanzar error, o intentar continuar. Aquí lanzamos error por seguridad.
                raise ValueError(f"El archivo CSV está corrupto o incompleto. Faltan: {missing_cols}")

            # 3. LIMPIEZA PROFUNDA (Deep Cleaning)
            df = self._clean_inventory_data(df)
            
            logger.info(f"Inventario cargado exitosamente. Total productos válidos: {len(df)}")
            return df

        except Exception as e:
            logger.critical(f"Error fatal leyendo el inventario: {e}", exc_info=True)
            return pd.DataFrame(columns=self.REQUIRED_COLUMNS.keys())

    def _clean_inventory_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Método interno para limpiar datos sucios (espacios, tipos incorrectos, nulos).
        """
        initial_count = len(df)
        
        # --- Limpieza de IDs ---
        # Convertir a string, eliminar .0 si viene de excel (ej: "123.0" -> "123"), eliminar espacios
        df['id'] = df['id'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
        
        # Eliminar filas donde el ID sea vacío o 'nan' literal tras la conversión
        df = df[df['id'] != 'nan']
        df = df[df['id'] != '']
        
        # Eliminamos duplicados por ID, manteniendo el último actualizado
        df = df.drop_duplicates(subset=['id'], keep='last')

        # --- Limpieza de Textos ---
        # Capitalizar nombres y limpiar espacios extra "  Aceite  " -> "Aceite"
        df['name'] = df['name'].astype(str).str.strip().str.title()
        df['supplier_name'] = df['supplier_name'].astype(str).str.strip()
        
        # --- Limpieza de Números ---
        # Convertir a numérico, coercing errores (texto en precio se vuelve NaN y luego 0)
        numeric_cols = ['quantity', 'purchase_price', 'sale_price', 'min_stock_alert']
        for col in numeric_cols:
            # pd.to_numeric con errors='coerce' transforma "veinte" en NaN en lugar de romper el programa
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            # Asegurar que no haya precios negativos
            if 'price' in col:
                df[col] = df[col].apply(lambda x: abs(x)) # Valor absoluto por si acaso

        # Convertir cantidad a entero si es necesario (opcional)
        df['quantity'] = df['quantity'].astype(int)
        
        # --- Manejo de Fechas ---
        if 'updated_at' in df.columns:
            df['updated_at'] = pd.to_datetime(df['updated_at'], errors='coerce').fillna(datetime.now())
        else:
            df['updated_at'] = datetime.now()

        # Reporte de limpieza
        dropped = initial_count - len(df)
        if dropped > 0:
            logger.warning(f"Se eliminaron {dropped} filas inválidas (IDs vacíos o duplicados).")
            
        return df

    def save_inventory(self, df: pd.DataFrame) -> bool:
        """
        Guarda el inventario de forma segura.
        """
        try:
            # Actualizar timestamp
            df['updated_at'] = datetime.now().isoformat()
            
            # Guardamos
            df.to_csv(self.inventory_file, index=False, encoding='utf-8')
            logger.info("Inventario guardado correctamente.")
            return True
        except Exception as e:
            logger.error(f"Error guardando inventario: {e}")
            return False

    def update_product_stock(self, product_id: str, quantity_change: int) -> Tuple[bool, str]:
        """
        Actualiza el stock de un producto específico.
        Retorna (Éxito, Mensaje).
        """
        df = self.load_inventory()
        
        # Buscar índice del producto (Búsqueda exacta por string)
        product_id = str(product_id).strip()
        mask = df['id'] == product_id
        
        if not mask.any():
            return False, f"Producto con ID {product_id} no encontrado."
            
        # Obtener stock actual
        current_stock = df.loc[mask, 'quantity'].values[0]
        new_stock = current_stock + quantity_change
        
        if new_stock < 0:
            return False, f"Stock insuficiente. Actual: {current_stock}, Solicitado: {abs(quantity_change)}"
            
        # Actualizar
        df.loc[mask, 'quantity'] = new_stock
        df.loc[mask, 'updated_at'] = datetime.now()
        
        if self.save_inventory(df):
            return True, f"Stock actualizado. Nuevo saldo: {new_stock}"
        else:
            return False, "Error al escribir en archivo."

    def get_low_stock_report(self) -> pd.DataFrame:
        """
        Genera un reporte de productos con bajo stock.
        """
        df = self.load_inventory()
        # Filtramos donde cantidad <= alerta
        low_stock = df[df['quantity'] <= df['min_stock_alert']]
        return low_stock[['id', 'name', 'quantity', 'supplier_name']]

# --- Bloque de Prueba (Solo se ejecuta si corres este archivo directamente) ---
if __name__ == "__main__":
    # Simulación de uso
    print("--- Iniciando Sistema de Datos Profesional ---")
    
    # 1. Instanciar
    # Asumimos que los archivos están en la raíz o ajusta la ruta '.'
    manager = AdvancedDataManager(data_folder=".") 
    
    # 2. Cargar
    print("Cargando inventario...")
    inventory = manager.load_inventory()
    
    # 3. Mostrar muestra
    if not inventory.empty:
        print("\nPrimeras 5 filas procesadas y limpias:")
        print(inventory[['id', 'name', 'quantity', 'sale_price']].head().to_string())
        
        # 4. Probar actualización
        pid_ejemplo = inventory['id'].iloc[0] # Tomamos el primer ID real
        exito, msg = manager.update_product_stock(pid_ejemplo, -1)
        print(f"\nPrueba de venta (-1 unidad): {msg}")
    else:
        print("El inventario está vacío o no se pudo leer.")
```

### ¿Qué hace a este código más profesional?

1.  **Manejo de Tipos (`dtype`)**:
    * **Problema anterior:** Python adivina los tipos. Si tu código de barras es `00750`, Excel/Python puede leerlo como el número `750`, perdiendo los ceros.
    * **Solución profesional:** `dtype={'id': str}`. Esto obliga a Python a leer esa columna como texto desde el primer milisegundo, conservando ceros a la izquierda y formatos largos como `7703616329376`.

2.  **Limpieza (`_clean_inventory_data`)**:
    * **Regex:** Usamos `regex` para eliminar el molesto `.0` que Excel agrega a veces a los códigos de barras de texto.
    * **Coerción de errores:** Si en la columna de precio alguien escribió "Gratis" por error, el código no se rompe; lo convierte a `0.0` o `NaN` y sigue funcionando.
    * **Strings:** Usa `.strip().title()` para que "  ACEITE  " se convierta automáticamente en "Aceite" limpio.

3.  **Logging**:
    * En lugar de simples `print`, usamos `logging`. Esto te permite en el futuro guardar un archivo `errors.log` para saber qué pasó un martes a las 3 AM sin tener que estar mirando la pantalla.

4.  **Estructura de Clase**:
    * Todo está encapsulado en `AdvancedDataManager`. Esto hace que tu archivo `app.py` sea mucho más limpio, ya que solo tendrá que llamar a `manager.load_inventory()` y no preocuparse por cómo se abre el archivo.

### Cómo usarlo
Para usar este nuevo gestor en tu archivo `app.py` actual, solo necesitas cambiar la importación y la inicialización:

```python
# En app.py
from data_manager import AdvancedDataManager

# Inicialización
data_manager = AdvancedDataManager(data_folder=".") # "." indica la carpeta actual donde subiste los CSV

# Uso
inventory_df = data_manager.load_inventory()
