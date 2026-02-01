import streamlit as st
import pandas as pd
import time
from data_manager import DataManager
import gemini_utils

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Rapitienda Acuarela | Enterprise",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cargar CSS
def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

try:
    local_css("style.css")
except:
    pass # Evitar error si no carga estilos temporalmente

# --- INICIALIZACIÓN DE ESTADO ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None
if "cart" not in st.session_state:
    st.session_state.cart = []

db = DataManager()

# --- FUNCIONES DE UI ---

def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align: center; padding: 2rem;">
            <h1 style="color: #2563eb;">RAPITIENDA ACUARELA</h1>
            <p style="color: #64748b;">Sistema de Gestión Enterprise</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Iniciar Sesión", use_container_width=True)
            
            if submitted:
                user = db.verify_user(username, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.success("¡Bienvenido!")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos")

def sidebar_menu():
    with st.sidebar:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 2rem;">
            <div style="font-size: 3rem;">🛍️</div>
            <h3 style="margin:0;">ACUARELA</h3>
            <span style="background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: bold;">ENTERPRISE</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.write(f"Hola, **{st.session_state.user['name']}**")
        
        menu = st.radio(
            "Navegación",
            ["Dashboard", "Venta (POS)", "Inventario", "Historial", "Base de Datos", "Consultor IA"],
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        if st.button("Cerrar Sesión", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()
            
    return menu

# --- PÁGINAS ---

def dashboard_page():
    st.title("📊 Panel de Control")
    metrics = db.get_dashboard_metrics()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas Hoy", f"${metrics['sales_today']:,.0f}")
    c2.metric("Valor Inventario", f"${metrics['inventory_value']:,.0f}")
    c3.metric("Productos Activos", metrics['total_products'])
    c4.metric("Alerta Stock Bajo", metrics['low_stock'], delta_color="inverse")
    
    st.markdown("### 📈 Tendencias Recientes")
    df_sales = db.get_sales_history()
    if not df_sales.empty:
        df_sales['fecha'] = pd.to_datetime(df_sales['timestamp']).dt.date
        daily_sales = df_sales.groupby('fecha')['price'].sum()
        st.line_chart(daily_sales)

def pos_page():
    st.title("🛒 Punto de Venta")
    col_prods, col_cart = st.columns([2, 1])
    df_inv = db.get_inventory()
    
    with col_prods:
        st.subheader("Catálogo")
        search = st.text_input("🔍 Buscar", placeholder="Escanear código o escribir nombre...")
        filtered_df = df_inv.copy()
        if search:
            mask = filtered_df['name'].astype(str).str.lower().str.contains(search.lower()) | \
                   filtered_df['id'].astype(str).str.contains(search)
            filtered_df = filtered_df[mask]
        
        if not filtered_df.empty:
            selection = st.dataframe(
                filtered_df[['id', 'name', 'sale_price', 'quantity']],
                column_config={"sale_price": st.column_config.NumberColumn("Precio", format="$%d"), "quantity": "Stock"},
                use_container_width=True, selection_mode="single-row", on_select="rerun", hide_index=True
            )
            if selection.selection['rows']:
                idx = selection.selection['rows'][0]
                prod = filtered_df.iloc[idx]
                # Lógica Carrito
                in_cart = sum(i['qty'] for i in st.session_state.cart if i['id'] == prod['id'])
                if prod['quantity'] > in_cart:
                    found = False
                    for item in st.session_state.cart:
                        if item['id'] == prod['id']:
                            item['qty']+=1; found=True; break
                    if not found: st.session_state.cart.append({'id': prod['id'], 'name': prod['name'], 'sale_price': prod['sale_price'], 'qty': 1})
                    st.toast(f"+1 {prod['name']}")
                else: st.error("Stock insuficiente")

    with col_cart:
        st.subheader("Ticket")
        if st.session_state.cart:
            total = sum(i['qty']*i['sale_price'] for i in st.session_state.cart)
            for i, item in enumerate(st.session_state.cart):
                c1,c2,c3 = st.columns([3,1,1])
                c1.write(f"{item['name']} x{item['qty']}"); c2.write(f"${item['qty']*item['sale_price']}"); 
                if c3.button("x", key=f"d{i}"): st.session_state.cart.pop(i); st.rerun()
            st.divider(); st.markdown(f"### Total: ${total:,.0f}")
            pay = st.selectbox("Pago", ["Efectivo", "Nequi", "Tarjeta"])
            if st.button("Cobrar", type="primary", use_container_width=True):
                if db.register_sale(st.session_state.cart, total, pay):
                    st.session_state.cart = []; st.success("Venta Exitosa"); time.sleep(1); st.rerun()

def inventory_page():
    st.title("📦 Inventario")
    tab1, tab2 = st.tabs(["Ver Inventario", "Agregar Producto"])
    with tab1:
        df = db.get_inventory()
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="inv_ed")
        if st.button("Guardar Cambios"):
            edited.to_csv(db.files['inventory'], index=False)
            st.success("Guardado")
    with tab2:
        with st.form("new_prod"):
            name = st.text_input("Nombre")
            code = st.text_input("Código Barras")
            p_in = st.number_input("Costo", 0); p_out = st.number_input("Precio Venta", 0)
            qty = st.number_input("Cantidad", 1); prov = st.text_input("Proveedor")
            if st.form_submit_button("Crear"):
                db.add_product({'id': code if code else str(uuid.uuid4())[:8], 'name': name, 'purchase_price': p_in, 'sale_price': p_out, 'quantity': qty, 'supplier_name': prov, 'min_stock_alert': 5, 'updated_at': datetime.now().isoformat()})
                st.success("Creado")

def database_page():
    st.title("💾 Gestión de Base de Datos")
    st.info("Aquí puedes descargar toda la información de tu negocio en un solo archivo Excel, editarlo y volverlo a subir.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 1. Descargar Base de Datos")
        st.write("Genera un archivo `.xlsx` con hojas separadas para Inventario, Ventas, Detalles y Proveedores.")
        
        # Generar Excel en memoria
        excel_data = db.get_database_as_excel()
        
        st.download_button(
            label="📥 Descargar Excel Maestro",
            data=excel_data,
            file_name=f"SAVA_DB_Master_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    with col2:
        st.markdown("### 2. Importar/Restaurar Base de Datos")
        st.warning("⚠️ Esto sobrescribirá los datos actuales con los del archivo que subas.")
        
        uploaded_file = st.file_uploader("Sube tu archivo Excel (.xlsx)", type=['xlsx'])
        
        if uploaded_file:
            if st.button("🔄 Actualizar Base de Datos", type="primary"):
                success, msg = db.import_database_from_excel(uploaded_file)
                if success:
                    st.success(f"¡Éxito! {msg}")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(f"Error: {msg}")

def history_page():
    st.title("📜 Historial"); st.dataframe(db.get_sales_history(), use_container_width=True, hide_index=True)

def ai_page():
    st.title("🤖 IA"); st.write("Asistente Virtual Acuarela")
    q = st.chat_input("Consulta...")
    if q:
        st.write(f"Usuario: {q}")
        st.write("IA: (Análisis simulado) Recomiendo revisar el stock de lácteos.")

# --- ROUTING ---
if not st.session_state.logged_in:
    login_page()
else:
    sel = sidebar_menu()
    if sel == "Dashboard": dashboard_page()
    elif sel == "Venta (POS)": pos_page()
    elif sel == "Inventario": inventory_page()
    elif sel == "Historial": history_page()
    elif sel == "Base de Datos": database_page() # Nueva página
    elif sel == "Consultor IA": ai_page()
