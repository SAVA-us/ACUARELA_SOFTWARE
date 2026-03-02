import streamlit as st
import pandas as pd
import time
import secrets # Para generar IDs robustos
from datetime import datetime

# Importaciones corregidas y locales
from data_manager import DataManager
from barcode_manager import BarcodeHandler
from gemini_utils import analyze_business_data

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Rapitienda Acuarela | SAVA Enterprise",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cargar CSS
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except:
        pass

local_css("style.css")

# --- PATRÓN SINGLETON PARA BASE DE DATOS ---
# Esto previene problemas de concurrencia al inicializar la BD
@st.cache_resource
def get_db():
    return DataManager()

db = get_db()

# --- INICIALIZACIÓN DE ESTADO ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None
if "cart" not in st.session_state:
    st.session_state.cart = []
if "ai_chat" not in st.session_state:
    st.session_state.ai_chat = []

# --- FUNCIONES DE UI ---

def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align: center; padding: 2rem;">
            <h1 style="color: #2563eb;">RAPITIENDA ACUARELA</h1>
            <p style="color: #64748b;">Powered by SAVA Logistics Engine</p>
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
            <div style="font-size: 3rem;">🛒</div>
            <h3 style="margin:0;">ACUARELA</h3>
            <span style="background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: bold;">SAVA EDITION</span>
        </div>
        """, unsafe_allow_html=True)
        
        st.write(f"Operador: **{st.session_state.user['name']}**")
        
        menu = st.radio(
            "Navegación",
            ["📊 Dashboard", "🛒 Venta (POS)", "📦 Inventario", "📜 Historial", "💾 Base de Datos", "🤖 Consultor IA"],
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        if st.button("Cerrar Sesión", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.session_state.cart = []
            st.rerun()
            
    return menu.split(" ")[1] # Retornamos solo la palabra clave sin el emoji

# --- PÁGINAS ---

def dashboard_page():
    st.title("Panel de Control General")
    metrics = db.get_dashboard_metrics()
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas de Hoy", f"${metrics['sales_today']:,.0f}")
    c2.metric("Valor del Inventario", f"${metrics['inventory_value']:,.0f}")
    c3.metric("Total Referencias", metrics['total_products'])
    c4.metric("Alertas de Stock", metrics['low_stock'], delta_color="inverse")
    
    st.markdown("### 📈 Tendencias de Ventas")
    df_sales = db.get_sales_history()
    if not df_sales.empty:
        df_sales['fecha'] = pd.to_datetime(df_sales['timestamp']).dt.date
        daily_sales = df_sales.groupby('fecha')['price'].sum()
        st.line_chart(daily_sales)
    else:
        st.info("No hay datos de ventas suficientes para mostrar el gráfico.")

def pos_page():
    st.title("Punto de Venta (POS)")
    col_prods, col_cart = st.columns([2, 1])
    df_inv = db.get_inventory()
    
    with col_prods:
        st.subheader("Búsqueda Rápida")
        # Integración correcta con barcode_manager
        search = st.text_input("🔍 Escanear código de barras o escribir nombre:", key="pos_search")
        
        if search:
            results = BarcodeHandler.find_product(df_inv, search)
            if results:
                df_results = pd.DataFrame(results)
                # Formatear el dataframe para mostrar
                selection = st.dataframe(
                    df_results[['id', 'name', 'sale_price', 'quantity']],
                    column_config={
                        "id": "Código", "name": "Producto",
                        "sale_price": st.column_config.NumberColumn("Precio", format="$%d"), 
                        "quantity": "Stock"
                    },
                    use_container_width=True, selection_mode="single-row", on_select="rerun", hide_index=True
                )
                
                # Lógica de agregado al carrito basada en selección visual
                if selection.selection['rows']:
                    idx = selection.selection['rows'][0]
                    prod = df_results.iloc[idx]
                    
                    in_cart = sum(i['qty'] for i in st.session_state.cart if i['id'] == prod['id'])
                    
                    if pd.to_numeric(prod['quantity']) > in_cart:
                        found = False
                        for item in st.session_state.cart:
                            if item['id'] == prod['id']:
                                item['qty'] += 1
                                found = True
                                break
                        if not found: 
                            st.session_state.cart.append({
                                'id': prod['id'], 'name': prod['name'], 
                                'sale_price': prod['sale_price'], 
                                'purchase_price': prod.get('purchase_price', 0),
                                'qty': 1
                            })
                        st.toast(f"✅ Agregado: {prod['name']}")
                    else: 
                        st.error(f"❌ Stock insuficiente para: {prod['name']}")
            else:
                st.warning("No se encontraron productos.")
        else:
            st.info("Esperando ingreso de código o búsqueda...")

    with col_cart:
        st.subheader("Carrito de Compras")
        if st.session_state.cart:
            total = sum(i['qty'] * i['sale_price'] for i in st.session_state.cart)
            
            for i, item in enumerate(st.session_state.cart):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{item['name']}** x{item['qty']}")
                c2.write(f"${item['qty'] * item['sale_price']:,.0f}")
                if c3.button("🗑️", key=f"del_{i}"): 
                    st.session_state.cart.pop(i)
                    st.rerun()
            
            st.divider()
            st.markdown(f"<h3 style='text-align: right; color: #2563eb;'>Total: ${total:,.0f}</h3>", unsafe_allow_html=True)
            
            pay_method = st.selectbox("Método de Pago", ["Efectivo", "Transferencia/Nequi", "Tarjeta"])
            customer = st.text_input("Cliente (Opcional)", value="Cliente General")
            
            if st.button("Procesar Pago", type="primary", use_container_width=True):
                # Generador de ID robusto anti-colisiones (12 caracteres hex)
                order_id = secrets.token_hex(6) 
                
                if db.register_sale(order_id, st.session_state.cart, total, pay_method, customer):
                    st.session_state.cart = []
                    st.success(f"Venta Exitosa registrada (ID: {order_id})")
                    time.sleep(1.5)
                    st.rerun()
                else:
                    st.error("Hubo un problema registrando la venta.")
        else:
            st.write("El carrito está vacío.")

def inventory_page():
    st.title("Gestión de Inventario")
    tab1, tab2 = st.tabs(["Ver y Editar Inventario", "Crear Nuevo Producto"])
    
    with tab1:
        st.info("Edita directamente las celdas y presiona 'Guardar Cambios' para actualizar la base de datos.")
        df = db.get_inventory()
        # Permitir edición dinámica
        edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="inv_ed")
        
        if st.button("Guardar Cambios al Inventario", type="primary"):
            db.update_inventory(edited)
            st.success("Inventario actualizado correctamente.")
            
    with tab2:
        with st.form("new_prod_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Nombre del Producto *")
                code = st.text_input("Código de Barras (Deja en blanco para autogenerar)")
                prov = st.text_input("Proveedor")
            with col2:
                p_in = st.number_input("Precio de Compra (Costo)", min_value=0.0)
                p_out = st.number_input("Precio de Venta *", min_value=0.0)
                qty = st.number_input("Cantidad Inicial", min_value=0)
                min_stock = st.number_input("Alerta de Stock Mínimo", value=5)
                
            submitted = st.form_submit_button("Añadir Producto")
            
            if submitted:
                if not name or p_out <= 0:
                    st.error("El nombre y el precio de venta son obligatorios.")
                else:
                    new_id = code.strip() if code.strip() else secrets.token_hex(4).upper()
                    new_prod = {
                        'id': new_id, 'name': name, 'purchase_price': p_in, 
                        'sale_price': p_out, 'quantity': qty, 'supplier_name': prov, 
                        'supplier_id': '', 'min_stock_alert': min_stock, 
                        'updated_at': datetime.now().isoformat()
                    }
                    db.add_product(new_prod)
                    st.success(f"Producto '{name}' añadido con éxito.")

def database_page():
    st.title("Respaldo y Base de Datos (Excel)")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Exportar DB Maestro")
        st.write("Descarga una copia completa de la base de datos en formato Excel (.xlsx). Contiene todas las hojas: inventario, ventas, detalles, proveedores y usuarios.")
        
        excel_bytes = db.get_database_as_bytes()
        
        st.download_button(
            label="📥 Descargar Base de Datos",
            data=excel_bytes,
            file_name=f"SAVA_Acuarela_DB_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    with col2:
        st.markdown("### Restaurar desde Backup")
        st.warning("⚠️ ¡Atención! Subir un archivo aquí **sobrescribirá completamente** la base de datos actual. Usa esto solo para restauraciones.")
        
        uploaded_file = st.file_uploader("Sube tu archivo .xlsx", type=['xlsx'])
        
        if uploaded_file:
            if st.button("🔄 Ejecutar Restauración", type="primary"):
                success, msg = db.import_database(uploaded_file)
                if success:
                    st.success(msg)
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(msg)

def history_page():
    st.title("Historial de Transacciones")
    df_sales = db.get_sales_history()
    
    if not df_sales.empty:
        # Ordenar por más recientes
        df_sales = df_sales.sort_values(by='timestamp', ascending=False)
        st.dataframe(df_sales, use_container_width=True, hide_index=True)
    else:
        st.info("No hay transacciones registradas todavía.")

def ai_page():
    st.title("SAVA IA - Consultor de Negocios")
    st.write("Analizando tu inventario y flujo de ventas actual para darte recomendaciones.")
    
    # Historial de chat en memoria
    for msg in st.session_state.ai_chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # Auto-diagnóstico inicial si no hay chat
    if not st.session_state.ai_chat:
        with st.spinner("Generando diagnóstico de la tienda..."):
            initial_response = analyze_business_data(db.get_inventory(), db.get_sales_history())
            st.session_state.ai_chat.append({"role": "assistant", "content": initial_response})
            st.rerun()

    query = st.chat_input("Pregunta a la IA sobre tus datos (ej. ¿Qué producto me deja más margen?)...")
    
    if query:
        # Añadir mensaje de usuario
        st.session_state.ai_chat.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)
            
        with st.chat_message("assistant"):
            with st.spinner("Analizando base de datos..."):
                response = analyze_business_data(db.get_inventory(), db.get_sales_history(), query)
                st.markdown(response)
                st.session_state.ai_chat.append({"role": "assistant", "content": response})

# --- ENRUTADOR PRINCIPAL ---
if not st.session_state.logged_in:
    login_page()
else:
    sel = sidebar_menu()
    if sel == "Dashboard": dashboard_page()
    elif sel == "Venta": pos_page()
    elif sel == "Inventario": inventory_page()
    elif sel == "Historial": history_page()
    elif sel == "Base": database_page()
    elif sel == "Consultor": ai_page()
