import google.generativeai as genai
import logging

class GeminiAssistant:
    def __init__(self, api_key: str):
        self.active = False
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
            self.active = True
        except Exception as e:
            logging.error(f"Error IA: {e}")

    def analyze_text(self, context_data: str, user_query: str) -> str:
        if not self.active:
            return "Error: IA no configurada correctamente."
            
        prompt = f"""
        Eres un consultor experto en retail para 'Rapitienda Acuarela'.
        
        CONTEXTO DEL NEGOCIO:
        {context_data}
        
        CONSULTA DEL USUARIO:
        "{user_query}"
        
        Responde con insights de negocio, recomendaciones de stock o análisis de ventas.
        Sé profesional pero conciso.
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"Error procesando solicitud: {e}"
