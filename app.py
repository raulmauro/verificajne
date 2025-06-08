import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import hashlib
import secrets
import string
import time
import plotly.express as px

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
                     inicio_informes TEXT,
                     fin_informes TEXT,
                     dni TEXT,
                     num_fic TEXT,
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

def cargar_fichas(partido_cod=None):
    try:
        df = pd.read_excel(ARCHIVO_FICHAS, dtype={'item': str, 'NUM_FIC': str, 'COD_OP': str, 'COD_DNI': str})
        required_cols = ['item', 'NUM_FIC', 'COD_OP', 'COD_DNI']
        if not all(col in df.columns for col in required_cols):
            raise ValueError(f"Archivo incompleto. Faltan columnas: {required_cols}")
        if partido_cod:
            return df[df['COD_OP'] == partido_cod]
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
                        except Exception as e:
                            st.error(f"Error al registrar: {str(e)}")

    with tab2:
        st.subheader("Asignación de Trabajo")
        fichas_df = cargar_fichas()
        if fichas_df is None:
            st.error("No se pudo cargar el archivo de fichas")
            return

        with st.expander("Asignar Fichas a Analistas"):
            with st.form("asignar_analistas"):
                partido_cod = st.selectbox("Partido", list(PARTIDOS.keys()), format_func=lambda x: PARTIDOS[x])
                fichas_partido = fichas_df[fichas_df['COD_OP'] == partido_cod]
                disponibles = len(fichas_partido)
                cantidad = st.number_input("Cantidad de fichas", min_value=1, max_value=disponibles, value=min(420, disponibles))
                usuario = st.selectbox("Analista",
                                      pd.read_sql("SELECT username FROM usuarios WHERE rol = 'analista'", conn)['username'].tolist())
                if st.form_submit_button("Asignar"):
                    conn = sqlite3.connect('jne_verification.db')
                    try:
                        c = conn.cursor()
                        fichas_a_asignar = fichas_partido.head(cantidad)
                        for _, ficha in fichas_a_asignar.iterrows():
                            c.execute('''SELECT 1 FROM asignaciones 
                                        WHERE dni = ? AND num_fic = ? AND tipo_asignacion = ?''',
                                     (ficha['COD_DNI'], ficha['NUM_FIC'], 'analista'))
                            if not c.fetchone():
                                conn.execute('''INSERT INTO asignaciones 
                                              (dni, num_fic, partido, asignado_a, tipo_asignacion, fecha_asignacion, completado)
                                              VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                          (ficha['COD_DNI'], ficha['NUM_FIC'], PARTIDOS[partido_cod],
                                           usuario, 'analista', datetime.now().strftime("%Y-%m-%d"), 0))
                        conn.commit()
                        st.success(f"{cantidad} fichas asignadas a {usuario}")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Error al asignar: {str(e)}")
                    finally:
                        conn.close()

    with tab3:
        st.subheader("Reportes de Progreso")
        conn = sqlite3.connect('jne_verification.db')
        try:
            df_analistas = pd.read_sql("SELECT * FROM analistas", conn)
            df_peritos = pd.read_sql("SELECT * FROM peritos", conn)

            st.write("**Progreso de Analistas**")
            st.dataframe(df_analistas)

            st.write("**Progreso de Peritos**")
            st.dataframe(df_peritos)
        finally:
            conn.close()

def analista_page():
    user = st.session_state['user']
    st.title(f"Formulario de Analista - {user['nombre']}")

    if 'asignaciones_analista' not in st.session_state:
        asignaciones = get_asignaciones_pendientes(user['id'], 'analista')
        st.session_state.asignaciones_analista = asignaciones
    else:
        asignaciones = st.session_state.asignaciones_analista

    if not asignaciones:
        st.warning("No tienes fichas asignadas para revisar hoy")
        return

    with st.form("encabezado_analista"):
        cols = st.columns(3)
        with cols[0]:
            fecha = st.date_input("Fecha", datetime.now())
        with cols[1]:
            partido = st.selectbox("Partido", list(PARTIDOS.values()))
        with cols[2]:
            turno = st.radio("Turno", ["Mañana", "Tarde"])
        cols = st.columns(2)
        with cols[0]:
            hora_inicio = st.time_input("Hora Inicio", datetime.now().time())
        with cols[1]:
            hora_fin = st.time_input("Hora Fin")
        if st.form_submit_button("Iniciar Jornada"):
            st.success("Jornada iniciada correctamente")

    MAX_FICHAS_POR_PAGINA = 10
    total_fichas = len(asignaciones)
    paginas = (total_fichas // MAX_FICHAS_POR_PAGINA) + (1 if total_fichas % MAX_FICHAS_POR_PAGINA else 0)
    pagina = st.number_input("Página", min_value=1, max_value=paginas, value=1)

    inicio = (pagina - 1) * MAX_FICHAS_POR_PAGINA
    fin = inicio + MAX_FICHAS_POR_PAGINA
    fichas_pagina = asignaciones[inicio:fin]

    resultados = []
    with st.form("verificacion_firmas"):
        for idx, ficha in enumerate(fichas_pagina):
            with st.expander(f"Ficha {ficha['num_fic']} - DNI: {ficha['dni']}", expanded=False):
                col_conforme, col_perito, col_obs = st.columns([1,1,3])
                conformes = col_conforme.checkbox("Conforme ✓", key=f"conforme_{idx}")
                para_perito = col_perito.checkbox("Para perito ⚠️", key=f"perito_{idx}")
                observaciones = col_obs.text_input("Observaciones", key=f"obs_{idx}")

                resultados.append({
                    'dni': ficha['dni'],
                    'num_fic': ficha['num_fic'],
                    'partido': ficha['partido'],
                    'conforme': conformes,
                    'para_perito': para_perito,
                    'observaciones': observaciones
                })

        if st.form_submit_button("Guardar Verificaciones"):
            try:
                conn = sqlite3.connect('jne_verification.db')
                cur = conn.cursor()
                for res in resultados:
                    cur.execute('''INSERT INTO analistas 
                                  (fecha, usuario, partido, turno, hora_inicio, hora_fin, 
                                   num_fic, dni, conforme, para_perito, observaciones, timestamp)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                               (fecha.strftime("%Y-%m-%d"), user['username'], partido, turno,
                                hora_inicio.strftime("%H:%M"), hora_fin.strftime("%H:%M"),
                                res['num_fic'], res['dni'], int(res['conforme']), 
                                int(res['para_perito']), res['observaciones'], 
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    
                    if res['para_perito']:
                        peritos = pd.read_sql("SELECT username FROM usuarios WHERE rol = 'perito'", conn)
                        if not peritos.empty:
                            perito = peritos.iloc[hash(res['dni']) % len(peritos)]['username']
                            cur.execute('''INSERT INTO asignaciones 
                                           (dni, num_fic, partido, asignado_a, tipo_asignacion, fecha_asignacion, completado)
                                           VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                        (res['dni'], res['num_fic'], res['partido'], perito, 'perito', 
                                         datetime.now().strftime("%Y-%m-%d"), 0))
                    
                    cur.execute('''UPDATE asignaciones SET completado = 1 
                                 WHERE dni = ? AND partido = ? AND tipo_asignacion = ?''',
                              (res['dni'], res['partido'], 'analista'))
                conn.commit()
                st.success("Verificaciones guardadas exitosamente")
                time.sleep(1)
                st.session_state.pop('asignaciones_analista', None)
                st.rerun()
            except Exception as e:
                conn.rollback()
                st.error(f"Error al guardar los datos: {str(e)}")
            finally:
                conn.close()

def perito_page():
    user = st.session_state['user']
    st.title(f"Formulario de Perito - {user['nombre']}")

    if 'asignaciones_perito' not in st.session_state:
        asignaciones = get_asignaciones_pendientes(user['id'], 'perito')
        st.session_state.asignaciones_perito = asignaciones
    else:
        asignaciones = st.session_state.asignaciones_perito

    if not asignaciones:
        st.warning("No tienes informes pendientes para hoy")
        return

    with st.form("encabezado_perito"):
        cols = st.columns(3)
        with cols[0]:
            fecha = st.date_input("Fecha", datetime.now())
        with cols[1]:
            partido = st.selectbox("Partido", list(PARTIDOS.values()))
        with cols[2]:
            traslado_reniec = st.time_input("Traslado RENIEC", value=datetime.now().time())
        col_inicio, col_fin = st.columns(2)
        with col_inicio:
            inicio_informes = st.time_input("Inicio Informes", value=datetime.now().time())
        with col_fin:
            fin_informes = st.time_input("Fin Informes")
        if st.form_submit_button("Iniciar Jornada"):
            st.success("Jornada iniciada correctamente")

    MAX_FICHAS_POR_PAGINA = 5
    total_fichas = len(asignaciones)
    paginas = (total_fichas // MAX_FICHAS_POR_PAGINA) + (1 if total_fichas % MAX_FICHAS_POR_PAGINA else 0)
    pagina = st.number_input("Página", min_value=1, max_value=paginas, value=1)

    inicio = (pagina - 1) * MAX_FICHAS_POR_PAGINA
    fin = inicio + MAX_FICHAS_POR_PAGINA
    casos_pagina = asignaciones[inicio:fin]

    resultados = []
    for idx, caso in enumerate(casos_pagina):
        with st.form(key=f"informe_pericial_{idx}"):
            with st.expander(f"Ficha: {caso['num_fic']} - DNI: {caso['dni']}", expanded=False):
                st.markdown(f"**Análisis Grafológico - Ficha: {caso['num_fic']} | DNI: {caso['dni']}**")
                col1, col2, col3 = st.columns([1,1,2])
                autentica = col1.checkbox("Auténtica ✓", key=f"aut_{idx}")
                falsa = col2.checkbox("Falsa ✗", key=f"fals_{idx}")
                tiempo_min = col3.number_input("Tiempo (min)", min_value=1, max_value=120, value=40, key=f"time_{idx}")

                observaciones = st.text_area("Observaciones técnicas", key=f"obs_{idx}")

                resultados.append({
                    'dni': caso['dni'],
                    'num_fic': caso['num_fic'],
                    'partido': caso['partido'],
                    'autentica': autentica,
                    'falsa': falsa,
                    'tiempo_min': tiempo_min,
                    'observaciones': observaciones
                })

            if st.form_submit_button("Guardar Informe"):
                try:
                    conn = sqlite3.connect('jne_verification.db')
                    cur = conn.cursor()
                    res = resultados[idx]

                    if not res['autentica'] and not res['falsa']:
                        st.error(f"Informe de DNI {res['dni']} debe tener una opción marcada")
                        continue

                    cur.execute('''INSERT INTO peritos 
                                  (fecha, usuario, partido, inicio_informes, fin_informes,
                                   dni, num_fic, autentica, falsa, tiempo_min, observaciones, timestamp)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                               (fecha.strftime("%Y-%m-%d"), user['username'], res['partido'],
                                inicio_informes.strftime("%H:%M"), fin_informes.strftime("%H:%M"),
                                res['dni'], res['num_fic'],
                                int(res['autentica']), int(res['falsa']),
                                res['tiempo_min'], res['observaciones'],
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

                    cur.execute('''UPDATE asignaciones SET completado = 1 
                                 WHERE dni = ? AND partido = ? AND tipo_asignacion = ?''',
                              (res['dni'], res['partido'], 'perito'))

                    conn.commit()
                    st.success("Informe guardado exitosamente")
                    time.sleep(1)
                    st.session_state.pop('asignaciones_perito', None)
                    st.rerun()

                except Exception as e:
                    conn.rollback()
                    st.error(f"Error al guardar los datos: {str(e)}")
                finally:
                    conn.close()

def reportes_page():
    st.title("📊 Reportes de Avance General")

    conn = sqlite3.connect('jne_verification.db')

    try:
        df_analistas = pd.read_sql("SELECT * FROM analistas", conn)
        df_peritos = pd.read_sql("SELECT * FROM peritos", conn)

        if not df_analistas.empty:
            analistas_group = df_analistas.groupby('usuario').agg(
                total_fichas=('num_fic', 'count'),
                conformes=('conforme', 'sum'),
                derivados=('para_perito', 'sum')
            ).reset_index()
            st.subheader("📈 Progreso por Analista")
            st.dataframe(analistas_group)

        else:
            st.info("No hay datos de analistas registrados aún.")

        if not df_peritos.empty:
            peritos_group = df_peritos.groupby('usuario').agg(
                informes_realizados=('id', 'count'),
                promedio_tiempo=('tiempo_min', 'mean'),
                autenticas=('autentica', 'sum'),
                falsas=('falsa', 'sum')
            ).reset_index()
            peritos_group['promedio_tiempo'] = peritos_group['promedio_tiempo'].round(1)
            st.subheader("⚖️ Progreso por Perito")
            st.dataframe(peritos_group)

        else:
            st.info("No hay datos de peritos registrados aún.")

        total_revisado = len(df_analistas)
        total_informes = len(df_peritos)
        completado = total_revisado + total_informes
        porcentaje_completado = (completado / TOTAL_FICHAS) * 100

        st.subheader("📦 Progreso General del Proyecto")
        st.metric(label="Fichas Completadas", value=f"{completado} / {TOTAL_FICHAS}")
        st.progress(int(porcentaje_completado))
        st.markdown(f"**{porcentaje_completado:.1f}% completado**")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 🔍 Análisis Preliminares")
            st.markdown(f"- Fichas revisadas: {len(df_analistas)}")
            st.markdown(f"- Derivadas a peritos: {df_analistas['para_perito'].sum()}")
        with col2:
            st.markdown("### 🧾 Informes Periciales")
            st.markdown(f"- Informes realizados: {len(df_peritos)}")
            st.markdown(f"- Auténticas: {df_peritos['autentica'].sum()}")
            st.markdown(f"- Falsas: {df_peritos['falsa'].sum()}")

    except Exception as e:
        st.error(f"Error al generar los reportes: {str(e)}")
    finally:
        conn.close()

# --- MAIN ---
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

        menu = ["Inicio", "Ver Reportes"]
        if user['rol'] == 'admin':
            menu.insert(1, "Panel de Administración")
        elif user['rol'] == 'analista':
            menu.insert(1, "Formulario de Analista")
        elif user['rol'] == 'perito':
            menu.insert(1, "Formulario de Perito")

        choice = st.sidebar.selectbox("Navegar", menu)

        if choice == "Inicio":
            st.title("Bienvenido al Sistema JNE")
            st.write("Selecciona una opción desde el menú lateral.")
        elif choice == "Panel de Administración":
            admin_page()
        elif choice == "Formulario de Analista":
            analista_page()
        elif choice == "Formulario de Perito":
            perito_page()
        elif choice == "Ver Reportes":
            reportes_page()

if __name__ == "__main__":
    init_db()
    create_admin_user()
    main()
