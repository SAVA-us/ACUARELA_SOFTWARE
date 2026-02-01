import pandas as pd
from typing import List, Dict

class BarcodeHandler:
    @staticmethod
    def find_product(df: pd.DataFrame, query: str) -> List[Dict]:
        """Búsqueda universal de productos."""
        if df.empty or not query:
            return []
            
        query = str(query).strip().lower()
        
        # 1. Búsqueda exacta ID
        id_match = df[df['id'].astype(str) == query]
        if not id_match.empty:
            return id_match.to_dict('records')
            
        # 2. Búsqueda nombre
        name_match = df[df['name'].str.lower().str.contains(query, na=False)]
        return name_match.head(10).to_dict('records') # Limitar resultados
