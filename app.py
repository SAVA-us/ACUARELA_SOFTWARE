import streamlit as st
import pandas as pd
from data_manager import AdvancedDataManager
from barcode_manager import BarcodeHandler
from gemini_utils import GeminiAssistant

# --- Configuración de la Página (Debe ser lo primero) ---
st.set_page_config(
    page_title="Acuarela Software",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Cargar Estilos CSS ---
def load_css():
    with open("style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# --- Inicialización de Servicios (Singleton) ---
@st.cache_resource
def get_managers():
    # Inicializa el gestor de datos
    dm = AdvancedDataManager()
    # Inicializa la IA (Intenta obtener la API key de secrets o input)
    api_key = st.secrets.get("GOOGLE_API_KEY", "") 
    ai = GeminiAssistant(api_key)
    return dm, ai

data_manager, ai_assistant = get_managers()

# --- Gestión de Estado (Session State) ---
if 'cart' not in st.session_state:
    st.session_state.cart = [] # Lista de diccionarios {'id', 'name', 'price', 'qty'}
if 'last_msg' not in st.session_state:
    st.session_state.last_msg = ""

# --- Funciones de UI ---

def add_to_cart(product, qty_to_add):
    """Añade producto al carrito virtual."""
    # Verificar stock real antes de añadir
    if qty_to_add > product['quantity']:
        st.error(f"Stock insuficiente. Solo quedan {product['quantity']}.")
        return

    # Buscar si ya está en el carrito
    found = False
    for item in st.session_state.cart:
        if item['id'] == product['id']:
            item['qty'] += qty_to_add
            found = True
            break
    
    if not found:
        st.session_state.cart.append({
            'id': product['id'],
            'name': product['name'],
            'price': product['sale_price'],
            'qty': qty_to_add
        })
    st.success(f"Añadido: {product['name']}")

def process_sale():
    """Finaliza la venta y descuenta inventario."""
    if not st.session_state.cart:
        st.warning("El carrito está vacío.")
        return

    total_items = 0
    errors = []

    for item in st.session_state.cart:
        success, msg = data_manager.update_stock(item['id'], -item['qty'])
        if success:
            total_items += 1
        else:
            errors.append(f"{item['name']}: {msg}")

    if errors:
        st.error(f"Problemas al procesar: {', '.join(errors)}")
    else:
        st.balloons()
        st.success("¡Venta registrada correctamente!")
        st.session_state.cart = [] # Limpiar carrito
        st.rerun() # Recargar para ver stock actualizado

# --- Layout Principal ---

st.title("🎨 Sistema de Gestión Acuarela")

# Sidebar
with st.sidebar:
    st.header("Herramientas")
    api_input = st.text_input("Gemini API Key", type="password", help="Necesaria para el Asistente AI")
    if api_input:
        ai_assistant = GeminiAssistant(api_input) # Reinicializar con key
    
    st.info("💡 Escanea un código en la pestaña 'Punto de Venta'")

# Tabs
tab1, tab2, tab3 = st.tabs(["🛒 Punto de Venta", "📦 Inventario", "🤖 Asistente IA"])

# --- TAB 1: PUNTO DE VENTA (POS) ---
with tab1:
    col_search, col_cart = st.columns([2, 1])

    with col_search:
        st.subheader("Búsqueda de Productos")
        search_query = st.text_input("Escanear Código o Buscar Nombre", key="pos_search")
        
        if search_query:
            df_inv = data_manager.load_inventory()
            results = BarcodeHandler.find_product(df_inv, search_query)
            
            if not results:
                st.warning("No se encontraron productos.")
            else:
                for p in results:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([3, 1, 1])
                        with c1:
                            st.markdown(f"**{p['name']}**")
                            st.caption(f"ID: {p['id']} | Stock: {p['quantity']}")
                        with c2:
                            st.markdown(f"**${p['sale_price']:,.0f}**")
                        with c3:
                            if st.button("Añadir", key=f"add_{p['id']}"):
                                add_to_cart(p, 1)

    with col_cart:
        st.subheader("Carrito de Compras")
        if st.session_state.cart:
            total = 0
            for i, item in enumerate(st.session_state.cart):
                subtotal = item['price'] * item['qty']
                total += subtotal
                st.markdown(f"{item['qty']}x {item['name']} - **${subtotal:,.0f}**")
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state.cart.pop(i)
                    st.rerun()
            
            st.divider()
            st.metric("Total a Pagar", f"${total:,.0f}")
            
            if st.button("✅ Finalizar Venta", type="primary", use_container_width=True):
                process_sale()
        else:
            st.info("El carrito está vacío.")

# --- TAB 2: INVENTARIO ---
with tab2:
    st.subheader("Gestión de Stock")
    df_inventory = data_manager.load_inventory()
    
    # Filtros
    filter_txt = st.text_input("Filtrar inventario", placeholder="Escribe para filtrar...")
    if filter_txt:
        df_show = df_inventory[df_inventory['name'].str.contains(filter_txt, case=False, na=False)]
    else:
        df_show = df_inventory

    # Editor de datos interactivo
    st.data_editor(
        df_show,
        column_config={
            "sale_price": st.column_config.NumberColumn("Precio Venta", format="$%d"),
            "purchase_price": st.column_config.NumberColumn("Precio Compra", format="$%d"),
            "quantity": st.column_config.NumberColumn("Stock", help="Cantidad disponible"),
        },
        disabled=["id"], # No dejar editar IDs para no romper referencias
        hide_index=True,
        use_container_width=True
    )
    
    st.caption("Nota: La edición directa aquí es solo visual (por ahora). Usa el POS para movimientos de stock.")

# --- TAB 3: ASISTENTE IA ---
with tab3:
    st.subheader("Consultar al Asistente")
    user_q = st.text_area("Pregunta sobre tus ventas o inventario:", placeholder="¿Qué productos tienen bajo stock? ¿Cuál es el valor total del inventario?")
    
    if st.button("Analizar") and user_q:
        with st.spinner("Analizando datos..."):
            # Pasamos el dataframe actual
            df = data_manager.load_inventory()
            answer = ai_assistant.analyze_data(df, user_q)
            st.markdown(answer)

# Footer
st.markdown("---")
st.markdown("© 2024 Acuarela Software v2.0 | Sistema Robusto")
