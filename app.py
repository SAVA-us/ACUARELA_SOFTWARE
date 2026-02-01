import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_option_menu import option_menu
from data_manager import DataManager
from barcode_manager import BarcodeHandler
from gemini_utils import GeminiAssistant
import time

# --- Configuración Inicial ---
st.set_page_config(
    page_title="Rapitienda Acuarela | Enterprise",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cargar estilos
def load_css():
    with open("style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
load_css()

# --- Gestión de Estado e Inicialización ---
if 'manager' not in st.session_state:
    st.session_state.manager = DataManager()

if 'user' not in st.session_state:
    st.session_state.user = None # None significa no logueado

if 'cart' not in st.session_state:
    st.session_state.cart = []

manager = st.session_state.manager

# --- Módulo de Autenticación ---
def login_page():
    st.markdown("<div class='main-header'>🔐 Acceso al Sistema</div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info("Credenciales por defecto: admin / admin123")
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Ingresar", use_container_width=True)
            
            if submitted:
                user = manager.authenticate_user(username, password)
                if user:
                    st.session_state.user = user
                    st.success(f"Bienvenido {user['name']}")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")

def logout():
    st.session_state.user = None
    st.session_state.cart = []
    st.rerun()

# --- Vistas Principales ---

def dashboard_view():
    st.markdown("## 📊 Dashboard General")
    metrics = manager.get_dashboard_metrics()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas Totales", f"${metrics['total_sales']:,.0f}")
    c2.metric("Transacciones", metrics['transaction_count'])
    c3.metric("Valor Inventario", f"${metrics['inventory_value']:,.0f}")
    c4.metric("Alertas Stock", metrics['low_stock_count'], delta_color="inverse")
    
    st.markdown("---")
    
    # Gráficos
    df_sales = manager.get_sales_report()
    if not df_sales.empty:
        df_sales['date'] = pd.to_datetime(df_sales['date'])
        
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            st.subheader("Ventas por Día")
            daily_sales = df_sales.groupby(df_sales['date'].dt.date)['total'].sum().reset_index()
            fig = px.bar(daily_sales, x='date', y='total', color='total', template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
            
        with col_g2:
            st.subheader("Top Productos")
            top_prods = df_sales.groupby('product_name')['quantity'].sum().reset_index().sort_values('quantity', ascending=False).head(5)
            fig2 = px.pie(top_prods, values='quantity', names='product_name', hole=0.4)
            st.plotly_chart(fig2, use_container_width=True)

def pos_view():
    st.markdown("## 🛒 Punto de Venta")
    
    col_izq, col_der = st.columns([2, 1])
    
    with col_izq:
        # Buscador
        query = st.text_input("🔍 Escanear producto o buscar por nombre", key="pos_search")
        if query:
            df_inv = manager.load_inventory()
            results = BarcodeHandler.find_product(df_inv, query)
            
            if results:
                for p in results:
                    with st.container():
                        st.info(f"**{p['name']}** | Stock: {p['quantity']} | Precio: ${p['sale_price']:,.0f}")
                        if st.button(f"Agregar {p['name']}", key=f"add_{p['id']}"):
                            # Lógica de agregar al carrito
                            found = False
                            for item in st.session_state.cart:
                                if item['id'] == p['id']:
                                    item['qty'] += 1
                                    found = True
                                    break
                            if not found:
                                st.session_state.cart.append({
                                    'id': p['id'], 'name': p['name'], 'price': p['sale_price'], 'qty': 1
                                })
                            st.success("Agregado")
                            time.sleep(0.2)
                            st.rerun()
            else:
                st.warning("Producto no encontrado")

    with col_der:
        st.markdown("### 🛍️ Carrito")
        if st.session_state.cart:
            total = 0
            for i, item in enumerate(st.session_state.cart):
                subtotal = item['price'] * item['qty']
                total += subtotal
                st.markdown(f"**{item['name']}**")
                c_qty, c_del = st.columns([2, 1])
                item['qty'] = c_qty.number_input("Cant", 1, 100, item['qty'], key=f"qty_{i}", label_visibility="collapsed")
                if c_del.button("❌", key=f"del_{i}"):
                    st.session_state.cart.pop(i)
                    st.rerun()
                st.markdown(f"Subtotal: ${subtotal:,.0f}")
                st.divider()
            
            st.markdown(f"### Total: ${total:,.0f}")
            
            payment = st.selectbox("Método de Pago", ["Efectivo", "Tarjeta", "Transferencia"])
            
            if st.button("✅ Confirmar Venta", type="primary", use_container_width=True):
                if manager.register_sale(st.session_state.cart, payment, st.session_state.user['username']):
                    st.balloons()
                    st.success("Venta registrada correctamente")
                    st.session_state.cart = []
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Error al registrar venta. Verifica el stock.")
        else:
            st.info("El carrito está vacío")

def inventory_view():
    st.markdown("## 📦 Gestión de Inventario")
    
    tab1, tab2 = st.tabs(["Ver Inventario", "Agregar Producto"])
    
    with tab1:
        df = manager.load_inventory()
        st.dataframe(df, use_container_width=True, height=500)
        
        with st.expander("Descargar Reporte"):
            st.download_button("Descargar CSV", df.to_csv(index=False), "inventario.csv", "text/csv")
            
    with tab2:
        with st.form("add_prod"):
            c1, c2 = st.columns(2)
            pid = c1.text_input("Código de Barras (ID)")
            name = c2.text_input("Nombre del Producto")
            qty = c1.number_input("Cantidad Inicial", min_value=0)
            min_stock = c2.number_input("Alerta Stock Mínimo", min_value=1, value=5)
            p_buy = c1.number_input("Precio Compra", min_value=0.0)
            p_sell = c2.number_input("Precio Venta", min_value=0.0)
            supplier = st.text_input("Proveedor")
            
            if st.form_submit_button("Guardar Producto"):
                new_prod = {
                    "id": pid, "name": name, "quantity": qty, 
                    "purchase_price": p_buy, "sale_price": p_sell, 
                    "supplier_name": supplier, "min_stock_alert": min_stock
                }
                if manager.update_product(new_prod):
                    st.success("Producto guardado")
                else:
                    st.error("Error guardando producto")

def admin_view():
    st.markdown("## 👥 Administración de Usuarios")
    
    if st.session_state.user['role'] != 'admin':
        st.error("Acceso denegado. Se requieren permisos de administrador.")
        return

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Usuarios Registrados")
        users = manager.get_all_users()
        st.table(pd.DataFrame(users)[['username', 'name', 'role', 'created_at']])
        
    with c2:
        st.subheader("Crear Usuario")
        with st.form("new_user"):
            u_name = st.text_input("Usuario (Login)")
            u_real = st.text_input("Nombre Completo")
            u_pass = st.text_input("Contraseña", type="password")
            u_role = st.selectbox("Rol", ["staff", "admin"])
            
            if st.form_submit_button("Crear"):
                if manager.create_user(u_name, u_pass, u_role, u_real):
                    st.success("Usuario creado")
                    st.rerun()
                else:
                    st.error("Error: El usuario ya existe")

def ai_assistant_view():
    st.markdown("## 🤖 Asistente IA Gemini")
    
    api_key = st.text_input("Google API Key", type="password")
    
    if api_key:
        assistant = GeminiAssistant(api_key)
        prompt = st.text_area("Pregunta algo sobre tu negocio:")
        
        if st.button("Analizar") and prompt:
            with st.spinner("Pensando..."):
                df_inv = manager.load_inventory()
                df_sales = manager.get_sales_report()
                
                # Contexto enriquecido para la IA
                context = f"""
                Inventario Total: {len(df_inv)} productos.
                Valor Inventario: ${ (df_inv['quantity']*df_inv['sale_price']).sum() }.
                Ventas Totales: ${ df_sales['total'].sum() if not df_sales.empty else 0 }.
                Datos Inventario (Muestra): {df_inv.head(10).to_string()}
                """
                
                response = assistant.analyze_text(context, prompt)
                st.markdown(response)
    else:
        st.info("Ingresa tu API Key para activar la inteligencia artificial.")

# --- Router Principal ---

def main():
    if not st.session_state.user:
        login_page()
    else:
        # Sidebar con Navegación Profesional
        with st.sidebar:
            st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=100)
            st.markdown(f"### Hola, {st.session_state.user['name']}")
            st.markdown(f"**Rol:** {st.session_state.user['role'].upper()}")
            
            selected = option_menu(
                menu_title="Menú Principal",
                options=["Dashboard", "Punto de Venta", "Inventario", "Usuarios", "IA Asistente", "Salir"],
                icons=["bar-chart", "cart", "box", "people", "robot", "box-arrow-right"],
                menu_icon="cast",
                default_index=0,
            )
        
        # Enrutamiento de vistas
        if selected == "Dashboard":
            dashboard_view()
        elif selected == "Punto de Venta":
            pos_view()
        elif selected == "Inventario":
            inventory_view()
        elif selected == "Usuarios":
            admin_view()
        elif selected == "IA Asistente":
            ai_assistant_view()
        elif selected == "Salir":
            logout()

if __name__ == "__main__":
    main()
