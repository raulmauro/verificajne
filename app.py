import streamlit as st
import pandas as pd
from sqlite3 import dbapi2 as sqlite3
from datetime import datetime
import hashlib
import secrets
import string
import time

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Sistema JNE - Verificación Firmas", layout="wide")

# --- CONSTANTES ---
ARCHIVO_FICHAS = "fichas.xlsx"
PARTIDOS = {
    '1': 'Partido 1',
    '2': 'Partido 2'
}
TOTAL_FICHAS = 3596

# --- BASE DE DATOS CON MEJORAS DE SEGURIDAD Y CONTROL ---
def init_db():
    with sqlite3.connect('jne_verification.db') as conn:
        c = conn.cursor()
        # Usuarios con sal
        c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     username TEXT UNIQUE,
                     password TEXT,
                     salt TEXT,
                     nombre TEXT,
                     rol TEXT,
                     activo INTEGER)''')
        # Analistas
        c.execute('''CREATE TABLE IF NOT EXISTS analistas (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     fecha TEXT,
                     usuario TEXT,
                     partido TEXT,
                     turno TEXT,
                     hora_inicio TEXT,
                     hora_fin TEXT,
                     num_fic TEXT,
                     dni TEXT,
                     conforme INTEGER,
                     para_perito INTEGER,
                     observaciones TEXT,
                     timestamp TEXT,
                     FOREIGN KEY(usuario) REFERENCES usuarios(username))''')
        # Peritos
        c.execute('''CREATE TABLE IF NOT EXISTS peritos (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     fecha TEXT,
                     usuario TEXT,
                     partido TEXT,
                     traslado_reniec TEXT,
                     inicio_informes TEXT,
                     fin_informes TEXT,
                     dni TEXT,
                     autentica INTEGER,
                     falsa INTEGER,
                     tiempo_min INTEGER,
                     observaciones TEXT,
                     informe TEXT,
                     timestamp TEXT,
                     FOREIGN KEY(usuario) REFERENCES usuarios(username))''')
        # Asignaciones
        c.execute('''CREATE TABLE IF NOT EXISTS asignaciones (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     dni TEXT,
                     num_fic TEXT,
                     partido TEXT,
                     asignado_a TEXT,
                     tipo_asignacion TEXT,
                     fecha_asignacion TEXT,
                     completado INTEGER,
                     FOREIGN KEY(asignado_a) REFERENCES usuarios(username))''')
        # Historial de estados
        c.execute('''CREATE TABLE IF NOT EXISTS historial_estados (
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     dni TEXT,
                     num_fic TEXT,
                     partido TEXT,
                     estado_anterior TEXT,
                     estado_actual TEXT,
                     cambiado_por TEXT,
                     timestamp TEXT)''')
        conn.commit()

def create_admin_user():
    with sqlite3.connect('jne_verification.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM usuarios WHERE username='admin'")
        if not c.fetchone():
            salt = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
            hashed_password = hashlib.sha256(('admin123' + salt).encode()).hexdigest()
            c.execute("INSERT INTO usuarios (username, password, salt, nombre, rol, activo) VALUES (?, ?, ?, ?, ?, ?)",
                      ('admin', hashed_password, salt, 'Administrador', 'admin', 1))
            conn.commit()

# --- FUNCIONES AUXILIARES ---
def hash_password(password, salt=None):
    if salt is None:
        salt = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    return hashlib.sha256((password + salt).encode()).hexdigest(), salt

def login(username, password):
    with sqlite3.connect('jne_verification.db') as conn:
        c = conn.cursor()
        c.execute("SELECT id, username, password, salt, nombre, rol FROM usuarios WHERE username=? AND activo=1", (username,))
        user = c.fetchone()
        if user and user[2] == hashlib.sha256((password + user[3]).encode()).hexdigest():
            return {
                'id': user[0],
                'username': user[1],
                'nombre': user[4],
                'rol': user[5]
            }
    return None

def cargar_fichas():
    try:
        df = pd.read_excel(ARCHIVO_FICHAS, dtype={'item': str, 'NUM_FIC': str, 'COD_OP': str, 'COD_DNI': str})
        required_cols = ['item', 'NUM_FIC', 'COD_OP', 'COD_DNI']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"Archivo incompleto. Faltan columnas: {required_cols}")
        return df
    except Exception as e:
        st.error(f"Error al cargar fichas.xlsx: {str(e)}")
        return None

def get_asignaciones_pendientes(usuario_id, tipo):
    with sqlite3.connect('jne_verification.db') as conn:
        c = conn.cursor()
        c.execute('''SELECT a.dni, a.num_fic, a.partido 
                     FROM asignaciones a
                     JOIN usuarios u ON a.asignado_a = u.username
                     WHERE u.id = ? AND a.tipo_asignacion = ? AND a.completado = 0''',
                  (usuario_id, tipo))
        return [{'dni': row[0], 'num_fic': row[1], 'partido': row[2]} for row in c.fetchall()]

def marcar_completado(dni, partido, tipo):
    with sqlite3.connect('jne_verification.db') as conn:
        conn.execute('''UPDATE asignaciones 
                        SET completado = 1 
                        WHERE dni = ? AND partido = ? AND tipo_asignacion = ?''',
                     (dni, partido, tipo))

def cambiar_estado(dni, num_fic, partido, estado_anterior, estado_actual, usuario):
    with sqlite3.connect('jne_verification.db') as conn:
        conn.execute('''INSERT INTO historial_estados 
                      (dni, num_fic, partido, estado_anterior, estado_actual, cambiado_por, timestamp)
                      VALUES (?, ?, ?, ?, ?, ?, ?)''',
                   (dni, num_fic, partido, estado_anterior, estado_actual, usuario, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

# --- PÁGINAS ---
def login_page():
    st.title("Sistema de Verificación de Firmas - JNE")
    with st.form("login_form"):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Ingresar"):
            user = login(username, password)
            if user:
                st.session_state['user'] = user
                st.success(f"Bienvenido {user['nombre']}")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")

def admin_page():
    st.title("Panel de Administración")
    tab1, tab2, tab3 = st.tabs(["Usuarios", "Asignaciones", "Reportes"])
    with tab1:
        st.subheader("Gestión de Usuarios")
        with sqlite3.connect('jne_verification.db') as conn:
            usuarios = pd.read_sql("SELECT id, username, nombre, rol, activo FROM usuarios", conn)
            st.dataframe(usuarios)
            with st.expander("Crear Nuevo Usuario"):
                with st.form("nuevo_usuario"):
                    username = st.text_input("Nombre de usuario")
                    password = st.text_input("Contraseña", type="password")
                    nombre = st.text_input("Nombre completo")
                    rol = st.selectbox("Rol", ["analista", "perito", "admin"])
                    activo = st.checkbox("Activo", value=True)
                    if st.form_submit_button("Registrar"):
                        try:
                            hashed_pw, salt = hash_password(password)
                            conn.execute(
                                "INSERT INTO usuarios (username, password, salt, nombre, rol, activo) VALUES (?, ?, ?, ?, ?, ?)",
                                (username, hashed_pw, salt, nombre, rol, int(activo)))
                            conn.commit()
                            st.success("Usuario creado exitosamente")
                            time.sleep(1)
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("El nombre de usuario ya existe")
    # Otras pestañas sin cambios importantes...
    # (Puedes reutilizar el resto de las funciones originales ajustadas con las nuevas prácticas)

def analista_page():
    user = st.session_state['user']
    st.title(f"Formulario de Analista - {user['nombre']}")
    asignaciones = get_asignaciones_pendientes(user['id'], 'analista')
    if not asignaciones:
        st.warning("No tienes fichas asignadas para revisar hoy")
        return
    # (Continúa con el formulario de analista...)

def perito_page():
    user = st.session_state['user']
    st.title(f"Formulario de Perito - {user['nombre']}")
    asignaciones = get_asignaciones_pendientes(user['id'], 'perito')
    if not asignaciones:
        st.warning("No tienes informes pendientes para hoy")
        return
    # (Continúa con el formulario de perito...)

# --- APLICACIÓN PRINCIPAL ---
def main():
    if 'user' not in st.session_state:
        login_page()
    else:
        user = st.session_state['user']
        st.sidebar.title(f"Bienvenido, {user['nombre']}")
        st.sidebar.write(f"Rol: {user['rol'].capitalize()}")
        if st.sidebar.button("Cerrar Sesión"):
            st.session_state.clear()
            st.rerun()
        if user['rol'] == 'admin':
            admin_page()
        elif user['rol'] == 'analista':
            analista_page()
        elif user['rol'] == 'perito':
            perito_page()

if __name__ == "__main__":
    init_db()
    create_admin_user()
    main()
