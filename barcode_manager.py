import pandas as pd
from typing import Optional, Dict, List

class BarcodeHandler:
    """
    Clase especializada en interpretar la entrada del usuario (Scanner o Teclado).
    """
    
    @staticmethod
    def clean_input(input_val: str) -> str:
        """Limpia la entrada cruda del scanner."""
        if not input_val:
            return ""
        # Eliminar espacios y caracteres de control invisibles que a veces mandan los scanners
        return str(input_val).strip()

    @staticmethod
    def find_product(df: pd.DataFrame, query: str) -> List[Dict]:
        """
        Busca un producto por ID exacto O por coincidencia en el nombre.
        Retorna una lista de coincidencias.
        """
        if df.empty or not query:
            return []

        query = str(query).strip().lower()
        
        # 1. Búsqueda exacta por ID (Prioridad Alta)
        # Convertimos la columna id a string para comparar
        id_match = df[df['id'].astype(str) == query]
        if not id_match.empty:
            return id_match.to_dict('records')

        # 2. Búsqueda parcial por Nombre (Prioridad Media)
        # 'case=False' ignora mayúsculas/minúsculas
        name_match = df[df['name'].str.contains(query, case=False, na=False)]
        
        if not name_match.empty:
            return name_match.to_dict('records')
            
        return []
