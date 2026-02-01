import streamlit as st
import pandas as pd
import plotly.express as px
from data_manager import DataManager
from gemini_utils import configure_gemini, get_ai_response, analyze_image
from PIL import Image

# Configuración de la página
st.set_page_config(
    page_title="Acuarela Software ERP",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cargar CSS
with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Inicializar Gestor de Datos
@st.cache_resource
def get_data_manager():
    return DataManager(use_google_sheets=False)

dm = get_data_manager()
configure_gemini()

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.title("Acuarela Software")
    st.caption("Sistema Inteligente de Logística v2.0")
    
    menu = st.radio(
        "Navegación",
        ["📊 Dashboard", "📦 Inventario & Bodega", "🛒 Punto de Venta", "🤖 Asistente IA", "⚙️ Configuración"]
    )
    
    st.divider()
    st.info(f"Productos Cargados: {len(dm.inventory_df)}")
    
    # Simulación de estado de conexión
    st.success("Conectado: Base de Datos Local (CSV)")

# --- VISTA: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Panel de Control")
    
    kpis = dm.calculate_kpis()
    
    # Tarjetas de Métricas (Fila 1)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valor Venta Total", f"${kpis['inventory_value']:,.0f}")
    c2.metric("Costo Inversión", f"${kpis['inventory_cost']:,.0f}")
    c3.metric("Ganancia Potencial", f"${kpis['potential_profit']:,.0f}", delta_color="normal")
    c4.metric("Alertas Stock Bajo", kpis['low_stock'], delta_color="inverse")
    
    # Gráficos (Fila 2)
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("Top Productos por Stock")
        if not dm.inventory_df.empty:
            top_stock = dm.inventory_df.nlargest(10, 'quantity')
            fig = px.bar(top_stock, x='name', y='quantity', color='quantity', title="Mayor Disponibilidad")
            st.plotly_chart(fig, use_container_width=True)
            
    with col_chart2:
        st.subheader("Distribución de Precios")
        if not dm.inventory_df.empty:
            fig2 = px.histogram(dm.inventory_df, x='sale_price', nbins=20, title="Rango de Precios de Venta")
            st.plotly_chart(fig2, use_container_width=True)

# --- VISTA: INVENTARIO ---
elif menu == "📦 Inventario & Bodega":
    st.title("📦 Gestión de Inventario")
    
    tab1, tab2 = st.tabs(["Vista General", "Reposición Sugerida"])
    
    with tab1:
        st.caption("Edita directamente las celdas para actualizar stock o precios.")
        
        # Filtros
        search = st.text_input("🔍 Buscar producto por nombre o código", "")
        
        df_display = dm.inventory_df.copy()
        if search:
            df_display = df_display[
                df_display['name'].str.contains(search, case=False, na=False) | 
                df_display['id'].astype(str).str.contains(search)
            ]
            
        # Editor de Datos
        edited_df = st.data_editor(
            df_display,
            column_config={
                "sale_price": st.column_config.NumberColumn("Precio Venta", format="$%d"),
                "purchase_price": st.column_config.NumberColumn("Costo Compra", format="$%d"),
                "quantity": st.column_config.NumberColumn("Stock", help="Cantidad actual en bodega"),
                "min_stock_alert": st.column_config.NumberColumn("Alerta Min", help="Nivel para aviso de reorden"),
            },
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True
        )
        
        if st.button("💾 Guardar Cambios (Simulado)"):
            st.toast("Cambios guardados en memoria (Conecta GSheets para persistencia)", icon="✅")
            
    with tab2:
        st.subheader("⚠️ Productos con Stock Crítico")
        low_stock_df = dm.get_low_stock_items()
        if not low_stock_df.empty:
            st.error(f"Se encontraron {len(low_stock_df)} productos por debajo del mínimo.")
            st.dataframe(low_stock_df[['id', 'name', 'quantity', 'min_stock_alert', 'supplier_name']], use_container_width=True)
            
            if st.button("Generar Pedido Automático con IA"):
                prompt = "Genera un borrador de correo para los proveedores solicitando reabastecimiento de estos productos: " + low_stock_df['name'].to_string()
                with st.spinner("Redactando pedido..."):
                    suggestion = get_ai_response(prompt)
                    st.text_area("Borrador de Pedido:", suggestion, height=200)
        else:
            st.success("¡Todo el inventario está saludable!")

# --- VISTA: PUNTO DE VENTA ---
elif menu == "🛒 Punto de Venta":
    st.title("🛒 Caja / Punto de Venta")
    
    col_pos_left, col_pos_right = st.columns([2, 1])
    
    with col_pos_left:
        st.subheader("Agregar Productos")
        # Selector de productos
        product_list = dm.inventory_df['name'].tolist() if not dm.inventory_df.empty else []
        selected_product_name = st.selectbox("Seleccionar Producto", [""] + product_list)
        
        qty = st.number_input("Cantidad", min_value=1, value=1)
        
        if st.button("Agregar al Carrito"):
            if selected_product_name:
                prod = dm.inventory_df[dm.inventory_df['name'] == selected_product_name].iloc[0]
                # Lógica simple de carrito usando session_state
                if 'cart' not in st.session_state:
                    st.session_state.cart = []
                st.session_state.cart.append({
                    "name": prod['name'],
                    "price": prod['sale_price'],
                    "qty": qty,
                    "subtotal": prod['sale_price'] * qty
                })
                st.success(f"Agregado: {prod['name']}")

    with col_pos_right:
        st.subheader("🧾 Recibo Actual")
        if 'cart' in st.session_state and st.session_state.cart:
            cart_df = pd.DataFrame(st.session_state.cart)
            st.dataframe(cart_df, hide_index=True)
            
            total = cart_df['subtotal'].sum()
            st.metric("Total a Pagar", f"${total:,.0f}")
            
            if st.button("Finalizar Venta", type="primary"):
                st.balloons()
                st.session_state.cart = [] # Limpiar carrito
                st.success("Venta registrada exitosamente.")
        else:
            st.info("El carrito está vacío.")

# --- VISTA: ASISTENTE IA ---
elif menu == "🤖 Asistente IA":
    st.title("🤖 Acuarela Brain")
    st.markdown("Pregunta cualquier cosa sobre tu negocio. La IA tiene acceso a tus datos actuales.")
    
    # Historial de Chat
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ej: ¿Qué productos tienen margen de ganancia bajo?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analizando datos..."):
                # Pasamos el DataFrame entero como contexto
                response = get_ai_response(prompt, context_data=dm.inventory_df)
                st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})

# --- VISTA: CONFIGURACIÓN ---
elif menu == "⚙️ Configuración":
    st.title("Configuración del Sistema")
    st.write("Configura la conexión con Google Sheets y parámetros de la tienda.")
    
    with st.expander("🔗 Conexión Google Sheets"):
        st.warning("Actualmente usando modo: Archivos CSV Locales")
        st.text_input("ID de la Hoja de Cálculo (Google Sheet ID)")
        st.file_uploader("Subir credenciales.json (Google Service Account)")
        st.button("Probar Conexión")
