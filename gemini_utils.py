import google.generativeai as genai
import pandas as pd
import logging
import time

logger = logging.getLogger("AI_Assistant")

class GeminiAssistant:
    def __init__(self, api_key: str):
        if not api_key:
            logger.warning("API Key de Gemini no configurada. La IA estará desactivada.")
            self.model = None
        else:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
            except Exception as e:
                logger.error(f"Error configurando Gemini: {e}")
                self.model = None

    def analyze_data(self, df: pd.DataFrame, user_query: str) -> str:
        """
        Envía datos resumidos del inventario a la IA para obtener insights.
        """
        if not self.model:
            return "El servicio de IA no está disponible (Falta API Key o Error de conexión)."

        try:
            # Creamos un resumen ligero para no saturar el token limit
            # Solo enviamos columnas relevantes
            summary = df[['name', 'quantity', 'sale_price', 'supplier_name']].to_csv(index=False)
            
            # Si el CSV es muy grande, lo cortamos (ej: primeros 100 productos o resumen estadístico)
            if len(summary) > 10000:
                stats = df.describe().to_string()
                data_context = f"Estadísticas del Inventario:\n{stats}"
            else:
                data_context = f"Datos del Inventario (CSV):\n{summary}"

            prompt = f"""
            Actúa como un analista de negocios experto para la tienda 'Acuarela'.
            
            Contexto de datos:
            {data_context}
            
            Pregunta del usuario: "{user_query}"
            
            Instrucciones:
            1. Responde basándote estrictamente en los datos proporcionados.
            2. Sé conciso y da recomendaciones accionables.
            3. Si detectas productos con stock bajo (quantity < 5), menciónalos.
            """

            response = self.model.generate_content(prompt)
            return response.text

        except Exception as e:
            logger.error(f"Error generando respuesta de IA: {e}")
            return "Hubo un error al procesar tu consulta con la IA. Intenta de nuevo."
