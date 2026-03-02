import google.generativeai as genai
import os

def configure_gemini():
    """Configura la API key desde las variables de entorno."""
    api_key = os.environ.get("GOOGLE_API_KEY", "") 
    if api_key:
        genai.configure(api_key=api_key)
        return True
    return False

def get_gemini_response(prompt_text):
    """
    Envía un prompt al modelo Gemini Flash y retorna la respuesta.
    """
    if not configure_gemini():
        return "⚠️ La clave GOOGLE_API_KEY no está configurada. Por favor, añádela a tus variables de entorno para usar el Consultor IA."

    try:
        model = genai.GenerativeModel('gemini-2.5-flash-preview-09-2025')
        response = model.generate_content(prompt_text)
        return response.text
    except Exception as e:
        return f"Error en el servicio de IA: {str(e)}"

def analyze_business_data(inventory_df, sales_df, user_query=None):
    """
    Construye un prompt de contexto empresarial enviando datos reales de la BD Excel.
    """
    # Preparación de datos agregados (no enviamos toda la base, sino resúmenes para no superar límites de tokens)
    total_sales = sales_df['price'].sum() if not sales_df.empty else 0
    total_orders = len(sales_df) if not sales_df.empty else 0
    
    if not inventory_df.empty:
        total_inv_value = (pd.to_numeric(inventory_df['quantity'], errors='coerce') * pd.to_numeric(inventory_df['sale_price'], errors='coerce')).sum()
        low_stock_items = inventory_df[pd.to_numeric(inventory_df['quantity'], errors='coerce') <= 3]['name'].tolist()
        low_stock_str = ", ".join(low_stock_items[:5]) + ("..." if len(low_stock_items) > 5 else "")
    else:
        total_inv_value = 0
        low_stock_str = "Ninguno"

    base_context = f"""
    Eres SAVA-IA, un consultor experto en retail y logística para 'Rapitienda Acuarela'.
    Contexto actual del negocio:
    - Ventas históricas totales: ${total_sales:,.2f} en {total_orders} pedidos.
    - Valorización del inventario actual: ${total_inv_value:,.2f}
    - Productos con stock crítico: {low_stock_str}
    """
    
    if user_query:
        prompt = f"{base_context}\n\nPregunta del usuario: {user_query}\n\nProporciona una respuesta concisa, analítica y orientada a la toma de decisiones."
    else:
        prompt = f"{base_context}\n\nProporciona un diagnóstico general de la tienda en 2 párrafos, destacando recomendaciones urgentes de reabastecimiento si aplica."

    return get_gemini_response(prompt)
