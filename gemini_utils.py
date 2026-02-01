import google.generativeai as genai
import os
import pandas as pd

# Intenta obtener API KEY del entorno, sino deja vacío (el usuario deberá configurarlo)
api_key = os.getenv("GOOGLE_API_KEY", "")

def configure_gemini():
    if api_key:
        genai.configure(api_key=api_key)

def get_ai_response(prompt, context_data=None):
    """
    Genera respuesta de Gemini usando datos del inventario como contexto.
    """
    try:
        if not api_key:
            return "⚠️ Por favor configura tu GOOGLE_API_KEY en el sistema."

        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        
        # Construir contexto
        context_str = ""
        if context_data is not None:
            if isinstance(context_data, pd.DataFrame):
                # Resumir datos para no exceder tokens: Estadísticas y primeros 50 items
                stats = context_data.describe().to_string()
                sample = context_data.head(50).to_string()
                context_str = f"DATOS DE INVENTARIO (Muestra):\n{sample}\n\nESTADÍSTICAS:\n{stats}\n"
            else:
                context_str = str(context_data)

        full_prompt = f"""
        Actúa como el gerente experto de la tienda 'Rapitienda Acuarela'.
        Tienes acceso a los siguientes datos del negocio:
        {context_str}
        
        Responde a la siguiente pregunta del usuario de forma útil, breve y basada en los datos:
        "{prompt}"
        """
        
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"Error en IA: {str(e)}"

def analyze_image(image_bytes):
    """Placeholder para visión por computadora (facturas, productos)"""
    pass
