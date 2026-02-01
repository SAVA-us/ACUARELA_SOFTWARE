import google.generativeai as genai
import os
import pandas as pd

# Configuración segura de la API Key
# Se asume que la key está en las variables de entorno o secrets de Streamlit
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    # Fallback para entorno de desarrollo si no está la env var
    api_key = "" # El sistema inyectará la clave automáticamente en tiempo de ejecución si se usa el template correcto

def configure_gemini():
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        print(f"Error configurando Gemini: {e}")
        return False

def get_ai_response(prompt, context_data=None):
    """
    Genera una respuesta de texto basada en un prompt y datos de contexto opcionales.
    
    :param prompt: Pregunta del usuario.
    :param context_data: DataFrame o diccionario con datos del inventario/ventas.
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        
        full_prompt = "Actúa como un analista experto en logística y retail para 'Acuarela Software'.\n"
        
        if context_data is not None:
            # Convertir datos a string para que la IA los lea (limitado a primeros 50 items para no saturar token limit)
            if isinstance(context_data, pd.DataFrame):
                data_summary = context_data.head(50).to_string()
                stats = context_data.describe().to_string()
                full_prompt += f"\nCONTEXTO DE DATOS ACTUALES:\n{data_summary}\n\nESTADÍSTICAS:\n{stats}\n\n"
            else:
                full_prompt += f"\nCONTEXTO:\n{str(context_data)}\n\n"
        
        full_prompt += f"PREGUNTA DEL USUARIO: {prompt}\n"
        full_prompt += "Respuesta concisa y accionable:"

        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"Lo siento, hubo un error al consultar a la IA: {str(e)}"

def analyze_image(image_data, prompt="Describe esta imagen para un inventario"):
    """
    Analiza imágenes (facturas, productos) usando Gemini Vision.
    """
    try:
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        response = model.generate_content([prompt, image_data])
        return response.text
    except Exception as e:
        return f"Error analizando imagen: {str(e)}"
