import streamlit as st
import pandas as pd
import plotly.express as px
from data_manager import DataManager
from gemini_utils import configure_gemini, get_ai_response, analyze_image
import time

# --- Configuración Inicial ---
st.set_page_config(page_title="Rapitienda Acuarela", page_icon="🏪", layout="wide")

# Cargar CSS personalizado
with open('style.css') as f:
    st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

# Inicializar Gestor de Datos (Singleton)
@st.cache_resource
def get_dm():
    return DataManager()

dm = get_dm()
configure_gemini()

# Estado de sesión para el Carrito de Compras
if 'cart' not in st.session_state:
    st.session_state.cart = []

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2897/2897785.png", width=80)
    st.title("Acuarela POS")
    st.markdown("---")
    menu = st.radio("Navegación", ["🛒 Punto de Venta", "📦 Inventario", "📊 Dashboard", "🤖 Asistente IA"])
    st.markdown("---")
    
    # KPIs rápidos en sidebar
    metrics = dm.calculate_metrics()
    st.metric("Valor Inventario", f"${metrics['total_value']:,.0f}")
    st.metric("Productos Activos", metrics['product_count'])

# --- LÓGICA DE PÁGINAS ---

if menu == "🛒 Punto de Venta":
    st.header("🛒 Caja Registradora")
    
    col1, col2 = st.columns([1.5, 1])
    
    with col1:
        st.subheader("Buscar Producto")
        # Buscador inteligente (filtra el DataFrame)
        search_term = st.text_input("Escanear código o escribir nombre", key="search_pos")
        
        products = dm.inventory_df
        if search_term:
            products = products[
                products['name'].str.contains(search_term, case=False, na=False) | 
                products['id'].str.contains(search_term, na=False)
            ]
        
        # Mostrar resultados como tabla seleccionable (simulando grid de productos)
        if not products.empty:
            for index, row in products.head(5).iterrows():
                with st.container():
                    c_img, c_info, c_btn = st.columns([1, 3, 1])
                    with c_info:
                        st.markdown(f"**{row['name']}**")
                        st.caption(f"Stock: {row['quantity']} | Precio: ${row['sale_price']:,.0f}")
                    with c_btn:
                        if st.button("➕", key=f"add_{row['id']}"):
                            # Lógica agregar al carrito
                            existing = next((item for item in st.session_state.cart if item['id'] == row['id']), None)
                            if existing:
                                existing['qty'] += 1
                                existing['subtotal'] = existing['qty'] * existing['price']
                            else:
                                st.session_state.cart.append({
                                    "id": row['id'],
                                    "name": row['name'],
                                    "price": row['sale_price'],
                                    "qty": 1,
                                    "subtotal": row['sale_price']
                                })
                            st.toast(f"Agregado: {row['name']}")
                            st.rerun()
            if len(products) > 5:
                st.info("Muestra limitada a 5 productos. Refina tu búsqueda.")
        else:
            st.warning("No se encontraron productos.")

    with col2:
        st.subheader("🧾 Ticket Actual")
        if st.session_state.cart:
            cart_df = pd.DataFrame(st.session_state.cart)
            
            # Mostrar tabla editable del carrito
            edited_cart = st.data_editor(
                cart_df, 
                column_config={
                    "name": "Producto",
                    "qty": st.column_config.NumberColumn("Cant.", min_value=1, max_value=100),
                    "price": st.column_config.NumberColumn("Precio", format="$%d"),
                    "subtotal": st.column_config.NumberColumn("Subtotal", format="$%d"),
                    "id": None # Ocultar ID
                },
                disabled=["name", "price", "subtotal"],
                hide_index=True,
                use_container_width=True,
                key="cart_editor"
            )
            
            # Actualizar totales si se edita la cantidad
            # (Nota: La edición compleja requiere callback, por simplicidad recalculamos al recargar)
            
            total = sum(item['subtotal'] for item in st.session_state.cart)
            st.markdown(f"### Total: ${total:,.0f}")
            
            payment_method = st.selectbox("Método de Pago", ["Efectivo", "Nequi/Daviplata", "Tarjeta"])
            
            if st.button("✅ Finalizar Venta", use_container_width=True, type="primary"):
                # Procesar venta
                with st.spinner("Procesando..."):
                    # 1. Descontar inventario
                    for item in st.session_state.cart:
                        dm.update_stock(item['id'], -item['qty'])
                    
                    # 2. Registrar orden
                    order_id = dm.record_sale(st.session_state.cart, total, payment_method)
                    
                    st.success(f"Venta {order_id} registrada!")
                    st.session_state.cart = [] # Limpiar carrito
                    time.sleep(1)
                    st.rerun()
                    
            if st.button("🗑️ Cancelar", use_container_width=True):
                st.session_state.cart = []
                st.rerun()
        else:
            st.info("El carrito está vacío.")

elif menu == "📦 Inventario":
    st.header("📦 Gestión de Inventario")
    
    # Editor masivo tipo Excel
    st.markdown("Edita precios y stock directamente en la tabla:")
    
    # Copia para editar
    df_editable = dm.inventory_df.copy()
    
    edited_df = st.data_editor(
        df_editable,
        column_config={
            "name": "Producto",
            "quantity": st.column_config.NumberColumn("Stock Actual", help="Cantidad en bodega"),
            "sale_price": st.column_config.NumberColumn("Precio Venta", format="$%d"),
            "purchase_price": st.column_config.NumberColumn("Costo", format="$%d"),
            "min_stock_alert": "Alerta Min.",
            "id": st.column_config.TextColumn("Código Barras", disabled=True)
        },
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic"
    )
    
    if st.button("💾 Guardar Cambios"):
        # Aquí iría la lógica para guardar de vuelta al CSV/Google Sheets
        # dm.save_data(edited_df)
        st.toast("Cambios guardados en memoria (Connectar GSheets para persistencia)", icon="💾")

elif menu == "📊 Dashboard":
    st.header("📊 Inteligencia de Negocios")
    
    kpis = dm.calculate_metrics()
    
    # Fila 1: Métricas
    c1, c2, c3 = st.columns(3)
    c1.metric("Valor Total (P. Venta)", f"${kpis['total_value']:,.0f}")
    c2.metric("Costo Total", f"${kpis['total_cost']:,.0f}")
    c3.metric("Ganancia Esperada", f"${kpis['potential_profit']:,.0f}", delta="Margen Bruto")
    
    # Fila 2: Gráficos
    st.subheader("Análisis de Stock")
    if not dm.inventory_df.empty:
        # Top productos por valor
        dm.inventory_df['total_value'] = dm.inventory_df['quantity'] * dm.inventory_df['sale_price']
        top_valuable = dm.inventory_df.nlargest(10, 'total_value')
        
        fig = px.bar(top_valuable, x='name', y='total_value', title="Productos con más valor acumulado ($)")
        st.plotly_chart(fig, use_container_width=True)
        
        # Pie chart de categorías (si existiera columna categoria, sino usamos proveedor)
        if 'supplier_name' in dm.inventory_df.columns:
            fig2 = px.pie(dm.inventory_df, names='supplier_name', title="Distribución por Proveedor")
            st.plotly_chart(fig2, use_container_width=True)

elif menu == "🤖 Asistente IA":
    st.header("🤖 Acuarela Brain")
    st.info("Esta IA tiene acceso a tus datos de Excel actuales.")
    
    # Chat Interface
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if prompt := st.chat_input("Ej: ¿Qué productos necesito reponer urgentemente?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
            
        with st.chat_message("assistant"):
            with st.spinner("Analizando tus hojas de cálculo..."):
                # Enviamos el DataFrame como contexto a la IA
                response = get_ai_response(prompt, context_data=dm.inventory_df)
                st.write(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
