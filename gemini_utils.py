import google.generativeai as genai
import os

# Configuración básica
# Nota: La API Key se toma del entorno por seguridad en la plataforma
try:
    # Intenta obtener la API key del entorno o usa una cadena vacía para que el usuario la configure
    api_key = os.environ.get("GOOGLE_API_KEY", "") 
    genai.configure(api_key=api_key)
except:
    pass

def get_gemini_response(prompt_text):
    """
    Envía un prompt al modelo Gemini Flash y retorna la respuesta de texto.
    """
    try:
        # Usamos el modelo flash preview que es rápido y eficiente
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        
        response = model.generate_content(prompt_text)
        return response.text
    except Exception as e:
        return f"Error en el servicio de IA: {str(e)}. Por favor verifica tu API Key."

def analyze_business_data(inventory_df, sales_df):
    """
    Función auxiliar para preparar un prompt automático basado en dataframes
    """
    summary_inv = inventory_df.describe().to_string()
    total_sales = sales_df['price'].sum() if not sales_df.empty else 0
    
    prompt = f"""
    Analiza los siguientes datos de resumen de una tienda minorista:
    
    Resumen de Inventario:
    {summary_inv}
    
    Ventas Totales Históricas: ${total_sales}
    
    Provee un diagnóstico corto de 1 párrafo sobre la salud del inventario.
    """
    return get_gemini_response(prompt)
