import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import hashlib
import time
import os

# Configuración inicial
st.set_page_config(page_title="Sistema JNE - Verificación Firmas", layout="wide")

# --- CONSTANTES ---
ARCHIVO_FICHAS = "fichas.xlsx"  # Archivo con los datos de afiliados
PARTIDOS = {
    '1': 'Partido 1',  # COD_OP 1 = Partido 1
    '2': 'Partido 2'   # COD_OP 2 = Partido 2
}

# --- BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('jne_verification.db')
    c = conn.cursor()
    
    # Tabla de analistas
    c.execute('''CREATE TABLE IF NOT EXISTS analistas
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                  timestamp TEXT)''')
    
    # Tabla de peritos
    c.execute('''CREATE TABLE IF NOT EXISTS peritos
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                  timestamp TEXT)''')
    
    # Tabla de usuarios
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  nombre TEXT,
                  rol TEXT,
                  activo INTEGER)''')
    
    # Tabla de asignaciones
    c.execute('''CREATE TABLE IF NOT EXISTS asignaciones
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  dni TEXT,
                  num_fic TEXT,
                  partido TEXT,
                  asignado_a TEXT,
                  tipo_asignacion TEXT,
                  fecha_asignacion TEXT,
                  completado INTEGER)''')
    
    conn.commit()
    conn.close()

def create_admin_user():
    conn = sqlite3.connect('jne_verification.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM usuarios WHERE username='admin'")
    if not c.fetchone():
        hashed_password = hashlib.sha256('admin123'.encode()).hexdigest()
        c.execute("INSERT INTO usuarios (username, password, nombre, rol, activo) VALUES (?, ?, ?, ?, ?)",
                  ('admin', hashed_password, 'Administrador', 'admin', 1))
        conn.commit()
    
    conn.close()

# Inicializar DB
init_db()
create_admin_user()

# --- FUNCIONES AUXILIARES ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def login(username, password):
    conn = sqlite3.connect('jne_verification.db')
    c = conn.cursor()
    
    hashed_password = hash_password(password)
    c.execute("SELECT * FROM usuarios WHERE username=? AND password=? AND activo=1",
              (username, hashed_password))
    user = c.fetchone()
    
    conn.close()
    
    if user:
        return {
            'id': user[0],
            'username': user[1],
            'nombre': user[3],
            'rol': user[4]
        }
    return None

def cargar_fichas():
    """Carga los datos desde fichas.xlsx"""
    try:
        df = pd.read_excel(ARCHIVO_FICHAS, dtype={'item': str, 'NUM_FIC': str, 'COD_OP': str, 'COD_DNI': str})
        
        # Verificar columnas requeridas
        required_cols = ['item', 'NUM_FIC', 'COD_OP', 'COD_DNI']
        if not all(col in df.columns for col in required_cols):
            st.error(f"Error: El archivo debe contener las columnas: {', '.join(required_cols)}")
            return None
        
        return df
    
    except Exception as e:
        st.error(f"Error al cargar fichas.xlsx: {str(e)}")
        return None

def get_asignaciones_pendientes(usuario_id, tipo):
    """Obtiene asignaciones pendientes para un usuario"""
    conn = sqlite3.connect('jne_verification.db')
    c = conn.cursor()
    
    c.execute('''SELECT a.dni, a.num_fic, a.partido 
                 FROM asignaciones a
                 JOIN usuarios u ON a.asignado_a = u.username
                 WHERE u.id = ? AND a.tipo_asignacion = ? AND a.completado = 0''',
              (usuario_id, tipo))
    
    asignaciones = [{'dni': row[0], 'num_fic': row[1], 'partido': row[2]} for row in c.fetchall()]
    conn.close()
    
    return asignaciones

def marcar_completado(dni, partido, tipo):
    """Marca una asignación como completada"""
    conn = sqlite3.connect('jne_verification.db')
    c = conn.cursor()
    
    c.execute('''UPDATE asignaciones 
                 SET completado = 1 
                 WHERE dni = ? AND partido = ? AND tipo_asignacion = ?''',
              (dni, partido, tipo))
    
    conn.commit()
    conn.close()

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
        
        conn = sqlite3.connect('jne_verification.db')
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
                        hashed_pw = hash_password(password)
                        conn.execute("INSERT INTO usuarios (username, password, nombre, rol, activo) VALUES (?, ?, ?, ?, ?)",
                                    (username, hashed_pw, nombre, rol, int(activo)))
                        conn.commit()
                        st.success("Usuario creado exitosamente")
                        time.sleep(1)
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("El nombre de usuario ya existe")
        conn.close()
    
    with tab2:
        st.subheader("Asignación de Trabajo")
        
        fichas_df = cargar_fichas()
        if fichas_df is None:
            st.error("No se pudo cargar el archivo de fichas")
            return
        
        with st.expander("Asignar Fichas a Analistas"):
            with st.form("asignar_analistas"):
                partido_cod = st.selectbox("Partido", list(PARTIDOS.keys()), 
                                         format_func=lambda x: PARTIDOS[x])
                
                fichas_partido = fichas_df[fichas_df['COD_OP'] == partido_cod]
                disponibles = len(fichas_partido)
                st.info(f"Fichas disponibles para {PARTIDOS[partido_cod]}: {disponibles}")
                
                cantidad = st.number_input("Cantidad de fichas", min_value=1, 
                                         max_value=disponibles, 
                                         value=min(420, disponibles))
                
                usuario = st.selectbox("Analista", 
                                     pd.read_sql("SELECT username FROM usuarios WHERE rol = 'analista'", 
                                                sqlite3.connect('jne_verification.db'))['username'].tolist())
                
                if st.form_submit_button("Asignar"):
                    conn = sqlite3.connect('jne_verification.db')
                    try:
                        # Tomar las primeras 'cantidad' fichas no asignadas
                        fichas_a_asignar = fichas_partido.head(cantidad)
                        
                        for _, ficha in fichas_a_asignar.iterrows():
                            # Verificar si ya está asignada
                            c = conn.cursor()
                            c.execute('''SELECT 1 FROM asignaciones 
                                        WHERE dni = ? AND partido = ? AND completado = 0''',
                                    (ficha['COD_DNI'], PARTIDOS[partido_cod]))
                            if not c.fetchone():
                                conn.execute('''INSERT INTO asignaciones 
                                            (dni, num_fic, partido, asignado_a, tipo_asignacion, fecha_asignacion, completado) 
                                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                          (ficha['COD_DNI'], ficha['NUM_FIC'], PARTIDOS[partido_cod], 
                                           usuario, 'analista', datetime.now().strftime("%Y-%m-%d"), 0))
                        
                        conn.commit()
                        st.success(f"{cantidad} fichas asignadas a {usuario}")
                        time.sleep(2)
                        st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Error al asignar: {str(e)}")
                    finally:
                        conn.close()
    
    with tab3:
        st.subheader("Reportes de Progreso")
        
        conn = sqlite3.connect('jne_verification.db')
        
        st.write("**Progreso de Analistas**")
        analistas_progreso = pd.read_sql('''
            SELECT u.nombre, a.partido, COUNT(*) as fichas_revisadas, 
                   SUM(a.para_perito) as derivadas
            FROM analistas a
            JOIN usuarios u ON a.usuario = u.username
            GROUP BY u.nombre, a.partido
        ''', conn)
        st.dataframe(analistas_progreso)
        
        st.write("**Progreso de Peritos**")
        peritos_progreso = pd.read_sql('''
            SELECT u.nombre, p.partido, COUNT(*) as informes_realizados,
                   AVG(p.tiempo_min) as tiempo_promedio
            FROM peritos p
            JOIN usuarios u ON p.usuario = u.username
            GROUP BY u.nombre, p.partido
        ''', conn)
        st.dataframe(peritos_progreso)
        
        conn.close()

def analista_page():
    user = st.session_state['user']
    st.title(f"Formulario de Analista - {user['nombre']}")
    
    asignaciones = get_asignaciones_pendientes(user['id'], 'analista')
    
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
        
        st.form_submit_button("Iniciar Jornada")
    
    # Mostrar 20 fichas por página
    paginas = len(asignaciones) // 20 + (1 if len(asignaciones) % 20 else 0)
    pagina = st.number_input("Página", min_value=1, max_value=paginas, value=1)
    
    inicio = (pagina - 1) * 20
    fin = inicio + 20
    fichas_pagina = asignaciones[inicio:fin]
    
    with st.form("verificacion_firmas"):
        resultados = []
        for i, ficha in enumerate(fichas_pagina, start=1):
            with st.expander(f"Ficha {inicio + i} - {ficha['num_fic']} (DNI: {ficha['dni']})", expanded=False):
                cols = st.columns([1,1,3])
                with cols[0]:
                    conforme = st.checkbox("Conforme ✓", key=f"conforme_{i}")
                with cols[1]:
                    para_perito = st.checkbox("Para perito ⚠️", key=f"perito_{i}")
                with cols[2]:
                    observaciones = st.text_input("Observaciones", key=f"obs_{i}")
                
                # Espacio para visualización de firma (conexión externa)
                st.markdown("**Visualización de firma de referencia (conexión externa a RENIEC)**")
                
                resultados.append({
                    'dni': ficha['dni'],
                    'num_fic': ficha['num_fic'],
                    'partido': ficha['partido'],
                    'conforme': conforme,
                    'para_perito': para_perito,
                    'observaciones': observaciones
                })
        
        if st.form_submit_button("Guardar Verificaciones"):
            conn = sqlite3.connect('jne_verification.db')
            try:
                for res in resultados:
                    # Registrar en analistas
                    conn.execute('''INSERT INTO analistas 
                                  (fecha, usuario, partido, turno, hora_inicio, hora_fin, 
                                   num_fic, dni, conforme, para_perito, observaciones, timestamp)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                               (fecha.strftime("%Y-%m-%d"), user['username'], partido, turno,
                                hora_inicio.strftime("%H:%M"), hora_fin.strftime("%H:%M"),
                                res['num_fic'], res['dni'], int(res['conforme']), 
                                int(res['para_perito']), res['observaciones'], 
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    
                    # Si es para perito, crear asignación
                    if res['para_perito']:
                        peritos = pd.read_sql("SELECT username FROM usuarios WHERE rol = 'perito'", conn)
                        if not peritos.empty:
                            perito = peritos['username'][hash(res['dni']) % len(peritos)]  # Asignación balanceada
                            
                            conn.execute('''INSERT INTO asignaciones 
                                           (dni, num_fic, partido, asignado_a, tipo_asignacion, fecha_asignacion, completado)
                                           VALUES (?, ?, ?, ?, ?, ?, ?)''',
                                        (res['dni'], res['num_fic'], res['partido'], perito, 'perito', 
                                         datetime.now().strftime("%Y-%m-%d"), 0))
                    
                    # Marcar como completado para el analista
                    marcar_completado(res['dni'], res['partido'], 'analista')
                
                conn.commit()
                st.success("Verificaciones guardadas exitosamente")
                time.sleep(2)
                st.rerun()
            except Exception as e:
                conn.rollback()
                st.error(f"Error al guardar: {str(e)}")
            finally:
                conn.close()

def perito_page():
    user = st.session_state['user']
    st.title(f"Formulario de Perito - {user['nombre']}")
    
    asignaciones = get_asignaciones_pendientes(user['id'], 'perito')
    
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
            traslado_reniec = st.time_input("Traslado RENIEC", datetime.now().time())
        
        cols = st.columns(2)
        with cols[0]:
            inicio_informes = st.time_input("Inicio Informes")
        with cols[1]:
            fin_informes = st.time_input("Fin Informes")
        
        st.form_submit_button("Iniciar Jornada")
    
    caso_actual = st.selectbox("Seleccionar caso a analizar", 
                              [f"Ficha: {a['num_fic']} - DNI: {a['dni']}" for a in asignaciones])
    
    dni_seleccionado = asignaciones[[i for i, a in enumerate(asignaciones) 
                                   if f"Ficha: {a['num_fic']} - DNI: {a['dni']}" == caso_actual][0]['dni']
    num_fic_seleccionado = asignaciones[[i for i, a in enumerate(asignaciones) 
                                       if f"Ficha: {a['num_fic']} - DNI: {a['dni']}" == caso_actual][0]['num_fic']
    partido_seleccionado = asignaciones[[i for i, a in enumerate(asignaciones) 
                                      if f"Ficha: {a['num_fic']} - DNI: {a['dni']}" == caso_actual][0]['partido']
    
    with st.form("informe_pericial"):
        st.subheader(f"Análisis Grafólogico - Ficha: {num_fic_seleccionado} - DNI: {dni_seleccionado}")
        
        cols = st.columns([1,1,2])
        with cols[0]:
            autentica = st.checkbox("Auténtica ✓")
        with cols[1]:
            falsa = st.checkbox("Falsa ✗")
        with cols[2]:
            tiempo_min = st.number_input("Tiempo (minutos)", min_value=1, max_value=120, value=40)
        
        observaciones = st.text_area("Observaciones técnicas")
        informe = st.text_area("Informe detallado (mínimo 200 caracteres)", height=200)
        
        # Espacio para visualización de documentos (conexión externa)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Ficha electoral con firma a verificar**")
        with col2:
            st.markdown("**Registro original de firma (RENIEC)**")
        
        if st.form_submit_button("Guardar Informe"):
            if len(informe) < 200:
                st.error("El informe debe tener al menos 200 caracteres")
            else:
                conn = sqlite3.connect('jne_verification.db')
                try:
                    conn.execute('''INSERT INTO peritos 
                                  (fecha, usuario, partido, traslado_reniec, inicio_informes, fin_informes,
                                   dni, num_fic, autentica, falsa, tiempo_min, observaciones, informe, timestamp)
                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                               (fecha.strftime("%Y-%m-%d"), user['username'], partido_seleccionado,
                                traslado_reniec.strftime("%H:%M"), inicio_informes.strftime("%H:%M"),
                                fin_informes.strftime("%H:%M"), dni_seleccionado, num_fic_seleccionado,
                                int(autentica), int(falsa), tiempo_min, observaciones, informe,
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    
                    marcar_completado(dni_seleccionado, partido_seleccionado, 'perito')
                    
                    conn.commit()
                    st.success("Informe guardado exitosamente")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    conn.rollback()
                    st.error(f"Error al guardar: {str(e)}")
                finally:
                    conn.close()

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
    main()