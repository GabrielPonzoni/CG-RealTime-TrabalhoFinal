# =============================================================================
# Trabalho Final - Environment Mapping & Skybox
# Disciplina: Computação Gráfica em Tempo Real
#
# DESCRIÇÃO:
# Este script implementa a técnica de Environment Mapping utilizando um Cubemap.
# O ambiente virtual é renderizado através de um Skybox estático, que serve
# como base de iluminação e reflexão para superfícies paramétricas na cena.
#
# SHADER UNIFICADO PARA OBJETOS:
# Em vez de dois programas de shader separados (Phong e Reflexão), existe
# agora um único shader para todos os objetos da cena. O comportamento é
# controlado pelo uniform "u_modo" (int), passado via Python:
#
#   MODO_FOSCO     = 0  → iluminação Phong clássica (sem cubemap)
#   MODO_REFLEXIVO = 1  → reflexão pura via Environment Mapping (cubemap)
#
# Para configurar um objeto, basta chamar:
#   glUniform1i(glGetUniformLocation(Shader_objeto, "u_modo"), MODO_FOSCO)
#   glUniform3f(glGetUniformLocation(Shader_objeto, "objectColor"), R, G, B)
# ou:
#   glUniform1i(glGetUniformLocation(Shader_objeto, "u_modo"), MODO_REFLEXIVO)
#
# CONCEITOS TÉCNICOS APLICADOS:
# - GL_TEXTURE_CUBE_MAP: Mapeamento de textura em 6 faces independentes.
# - Amostragem 3D (vec3): Utilização dos próprios vértices do cubo como
#   vetores de direção para amostragem da textura, dispensando coordenadas UV.
# - Skybox Trick: Renderização do cubo de fundo forçando o depth test para
#   GL_LEQUAL, garantindo que o cenário seja sempre renderizado atrás da geometria.
# - Matriz de Visualização: Remoção da translação da view matrix no shader
#   do skybox, permitindo que a câmera rotacione sem "escapar" do cenário.
#
# TEXTURAS NECESSÁRIAS:
# - 6 texturas quadradas (right.jpg, left.jpg, top.jpg, bottom.jpg, front.jpg, back.jpg)
# - Diretório padrão: "CG-RealTime-TrabalhoFinal\\skybox"
#
# CONTROLES:
#   W/A/S/D - Movimentação da câmera
#   Mouse   - Rotação da câmera (FPS Look)
#   ESC     - Encerrar aplicação
#
# DEPENDÊNCIAS:
#   pip install PyOpenGL PyOpenGL_accelerate glfw Pillow numpy
# =============================================================================

import glfw
from OpenGL.GL import *
import OpenGL.GL.shaders
import numpy as np
import ctypes
import os
import math
from PIL import Image

# -----------------------------------------------------------------------------
# CONFIGURAÇÕES E VARIÁVEIS GLOBAIS
# -----------------------------------------------------------------------------

Window              = None
WIDTH, HEIGHT = 800, 600

# Shaders
Shader_skybox       = None      # shader exclusivo do skybox (sem transform, sem UV)
Shader_objeto       = None      # shader de objetos: fosco (Phong) OU reflexivo, via uniform u_modo

# Modos do shader unificado — passe via glUniform1i(... "u_modo" ...)
MODO_FOSCO     = 0   # iluminação Phong clássica
MODO_REFLEXIVO = 1   # reflexão pura via cubemap (Environment Mapping)

# VAOs e Contagem de Índices
Vao_skybox          = None
Objetos_cenario     = {}        # Dicionário para guardar (VAO, num_indices) de cada forma

# Texturas
Textura_cubemap     = None

Tempo_entre_frames = 0.0

# Pasta onde estão os 6 arquivos de textura do skybox
PASTA_SKYBOX    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skybox")

# -----------------------------
# Parâmetros da câmera virtual
# -----------------------------

Cam_speed  = 5.0
Cam_pos    = np.array([0.0, 0.0, 3.0])
Cam_yaw    = 0.0
Cam_pitch  = 0.0

lastX, lastY   = WIDTH / 2, HEIGHT / 2
primeiro_mouse = True

# -----------------------------------------------------------------------------
# CALLBACKS (TECLADO E MOUSE)
# -----------------------------------------------------------------------------

def redimensionaCallback(window, w, h):
	global WIDTH, HEIGHT
	WIDTH, HEIGHT = w, h

 
def mouse_callback(window, xpos, ypos):
	global lastX, lastY, primeiro_mouse, Cam_yaw, Cam_pitch

	if primeiro_mouse:
		lastX, lastY   = xpos, ypos
		primeiro_mouse = False

	xoffset = (xpos - lastX) * 0.1
	yoffset = (lastY - ypos) * 0.1
	lastX, lastY = xpos, ypos

	Cam_yaw   += xoffset
	Cam_pitch  = max(-89.0, min(89.0, Cam_pitch + yoffset))


def key_callback(window, key, scancode, action, mode):
	return

# -----------------------------
# Inicialização do OpenGL
# -----------------------------

def inicializaOpenGL():
	global Window

	glfw.init()
	Window = glfw.create_window(WIDTH, HEIGHT, "Trabalho Final - Tema 1", None, None)
	if not Window:
		glfw.terminate()
		exit()

	glfw.set_window_size_callback(Window, redimensionaCallback)
	glfw.make_context_current(Window)
	glfw.set_input_mode(Window, glfw.CURSOR, glfw.CURSOR_DISABLED)
	glfw.set_cursor_pos_callback(Window, mouse_callback)
	glfw.set_key_callback(Window, key_callback)
	glEnable(GL_DEPTH_TEST)

	print("Placa de vídeo:", glGetString(GL_RENDERER))
	print("Versão do OpenGL:", glGetString(GL_VERSION))
  

# -----------------------------------------------
# Geometria do skybox
# -----------------------------------------------
# O skybox é um cubo simples centrado na origem, com lado 1.
# NÃO usamos UVs aqui — as coordenadas de textura do cubemap são
# derivadas diretamente da posição do vértice (vec3), que serve como
# vetor de direção apontando para a face correta do cubemap.
#
# A ordem dos vértices segue a convenção do OpenGL para cubemaps:
# cada face é vista de dentro do cubo, então a ordem dos triângulos
# é invertida em relação ao cubo normal (face culling invertido).

def inicializaSkybox():
	global Vao_skybox

	Vao_skybox = glGenVertexArrays(1)
	glBindVertexArray(Vao_skybox)

	# Apenas posições (x, y, z) — sem UV, sem face_id
	# A posição do vértice É a direção de amostragem do cubemap
	vertices = np.array([
		# face DIREITA  (+X)
		 1.0, -1.0, -1.0,
		 1.0, -1.0,  1.0,
		 1.0,  1.0,  1.0,
		 1.0,  1.0,  1.0,
		 1.0,  1.0, -1.0,
		 1.0, -1.0, -1.0,
		# face ESQUERDA (-X)
		-1.0, -1.0,  1.0,
		-1.0, -1.0, -1.0,
		-1.0,  1.0, -1.0,
		-1.0,  1.0, -1.0,
		-1.0,  1.0,  1.0,
		-1.0, -1.0,  1.0,
		# face TOPO     (+Y)
		-1.0,  1.0, -1.0,
		 1.0,  1.0, -1.0,
		 1.0,  1.0,  1.0,
		 1.0,  1.0,  1.0,
		-1.0,  1.0,  1.0,
		-1.0,  1.0, -1.0,
		# face BASE     (-Y)
		-1.0, -1.0, -1.0,
		-1.0, -1.0,  1.0,
		 1.0, -1.0, -1.0,
		 1.0, -1.0, -1.0,
		-1.0, -1.0,  1.0,
		 1.0, -1.0,  1.0,
		# face FRENTE   (+Z)
		-1.0, -1.0,  1.0,
		-1.0,  1.0,  1.0,
		 1.0,  1.0,  1.0,
		 1.0,  1.0,  1.0,
		 1.0, -1.0,  1.0,
		-1.0, -1.0,  1.0,
		# face TRÁS     (-Z)
		-1.0,  1.0, -1.0,
		 1.0,  1.0, -1.0,
		 1.0, -1.0, -1.0,
		 1.0, -1.0, -1.0,
		-1.0, -1.0, -1.0,
		-1.0,  1.0, -1.0,
	], dtype=np.float32)

	vbo = glGenBuffers(1)
	glBindBuffer(GL_ARRAY_BUFFER, vbo)
	glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

	# Apenas atributo 0: posição (x, y, z)
	glEnableVertexAttribArray(0)
	glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 3 * 4, ctypes.c_void_p(0))

# -----------------------------------------------
# Geração Paramétrica Unificada (Esfera, Torus, Cone)
# -----------------------------------------------

def inicializaSuperficie(tipo='esfera', resolucao_u=30, resolucao_v=30):
	vertices = []
	indices = []
	
	passo_u = 1.0 / resolucao_u
	passo_v = 1.0 / resolucao_v
	largura = resolucao_v + 1

	# GERAÇÃO DOS VÉRTICES (Sem textura, apenas Posição e Normal)
	for i in range(resolucao_u + 1):
		u = i * passo_u
		for j in range(resolucao_v + 1):
			v = j * passo_v

			# --- BLOCO MATEMÁTICO ---
			if tipo == 'esfera':
				raio = 1.0
				phi = u * math.pi
				theta = v * 2.0 * math.pi
				
				x = raio * math.sin(phi) * math.cos(theta)
				y = raio * math.cos(phi)
				z = raio * math.sin(phi) * math.sin(theta)
				
				# Normal de uma esfera centrada na origem é a própria posição normalizada
				nx, ny, nz = x / raio, y / raio, z / raio

			elif tipo == 'torus':
				R_maior = 1.0
				r_menor = 0.3
				theta = u * 2.0 * math.pi
				phi = v * 2.0 * math.pi
				
				x = (R_maior + r_menor * math.cos(theta)) * math.cos(phi)
				y = (R_maior + r_menor * math.cos(theta)) * math.sin(phi)
				z = r_menor * math.sin(theta)
				
				# Normal analítica do Torus
				nx = math.cos(theta) * math.cos(phi)
				ny = math.cos(theta) * math.sin(phi)
				nz = math.sin(theta)

			elif tipo == 'cone':
				altura = 2.0
				raio = 1.0
				# u vai do topo (0) até a base (1)
				y = (altura / 2.0) - (u * altura)
				raio_atual = u * raio
				theta = v * 2.0 * math.pi
				
				x = raio_atual * math.cos(theta)
				z = raio_atual * math.sin(theta)
				
				# Normal analítica do Cone
				nx = altura * math.cos(theta)
				ny = raio
				nz = altura * math.sin(theta)
				norma = math.sqrt(nx*nx + ny*ny + nz*nz)
				nx, ny, nz = nx/norma, ny/norma, nz/norma

			# Adiciona: x, y, z, nx, ny, nz (6 floats por vértice)
			vertices.extend([x, y, z, nx, ny, nz])

	# GERAÇÃO DOS ÍNDICES
	for i in range(resolucao_u):
		for j in range(resolucao_v):
			sup_esq = i * largura + j
			sup_dir = sup_esq + 1
			inf_esq = (i + 1) * largura + j
			inf_dir = inf_esq + 1
			
			# Triângulos no sentido anti-horário
			indices.extend([sup_esq, inf_esq, sup_dir])
			indices.extend([sup_dir, inf_esq, inf_dir])

	# CONFIGURAÇÃO DOS BUFFERS
	vertices_data = np.array(vertices, dtype=np.float32)
	indices_data = np.array(indices, dtype=np.uint32)

	vao = glGenVertexArrays(1)
	vbo = glGenBuffers(1)
	ebo = glGenBuffers(1)

	glBindVertexArray(vao)
	
	glBindBuffer(GL_ARRAY_BUFFER, vbo)
	glBufferData(GL_ARRAY_BUFFER, vertices_data.nbytes, vertices_data, GL_STATIC_DRAW)
	
	glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
	glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices_data.nbytes, indices_data, GL_STATIC_DRAW)

	stride = 6 * 4  # 6 floats de 4 bytes

	# Atributo 0: Posição (3 floats)
	glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
	glEnableVertexAttribArray(0)

	# Atributo 1: Normal (3 floats)
	glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(12))
	glEnableVertexAttribArray(1)

	glBindVertexArray(0)
	
	return vao, len(indices_data)

# -----------------------------------------------
# Carregamento do Cubemap
# -----------------------------------------------
# Um cubemap é carregado face a face, cada uma com um target diferente:
#
#   GL_TEXTURE_CUBE_MAP_POSITIVE_X → right.png   (face direita)
#   GL_TEXTURE_CUBE_MAP_NEGATIVE_X → left.png    (face esquerda)
#   GL_TEXTURE_CUBE_MAP_POSITIVE_Y → top.png     (face superior)
#   GL_TEXTURE_CUBE_MAP_NEGATIVE_Y → bottom.png  (face inferior)
#   GL_TEXTURE_CUBE_MAP_POSITIVE_Z → front.png   (face frontal)
#   GL_TEXTURE_CUBE_MAP_NEGATIVE_Z → back.png    (face traseira)
#
# IMPORTANTE: faces do cubemap NÃO devem ser flipadas verticalmente.
# O sistema de coordenadas do cubemap já usa Y para cima nativamente.

def carregaCubemap(pasta):
	global Textura_cubemap

	faces = [
		("right.jpg",  GL_TEXTURE_CUBE_MAP_POSITIVE_X),
		("left.jpg",   GL_TEXTURE_CUBE_MAP_NEGATIVE_X),
		("top.jpg",    GL_TEXTURE_CUBE_MAP_POSITIVE_Y),
		("bottom.jpg", GL_TEXTURE_CUBE_MAP_NEGATIVE_Y),
		("front.jpg",  GL_TEXTURE_CUBE_MAP_POSITIVE_Z),
		("back.jpg",   GL_TEXTURE_CUBE_MAP_NEGATIVE_Z),
	]

	Textura_cubemap = glGenTextures(1)
	glBindTexture(GL_TEXTURE_CUBE_MAP, Textura_cubemap)
	glPixelStorei(GL_UNPACK_ALIGNMENT, 1)

	for nome, target in faces:
		caminho = os.path.join(pasta, nome)
		img     = Image.open(caminho).convert("RGB")   # cubemap usa RGB (sem alpha)
		# NÃO flipar — cubemap já tem Y para cima
		dados   = np.array(img, dtype=np.uint8)
		larg, alt = img.size

		glTexImage2D(target, 0, GL_RGB, larg, alt, 0,
					 GL_RGB, GL_UNSIGNED_BYTE, dados)
		print(f"  Face carregada: {nome} ({larg}x{alt})")

	# GL_LINEAR para suavidade nas bordas entre faces
	glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
	glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

	# GL_CLAMP_TO_EDGE em todos os 3 eixos: evita costuras visíveis
	# nas bordas onde duas faces do cubemap se encontram
	glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
	glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
	glTexParameteri(GL_TEXTURE_CUBE_MAP, GL_TEXTURE_WRAP_R, GL_CLAMP_TO_EDGE)

	print(f"Cubemap carregado: {pasta}/")

# -----------------------------------------------
# Shaders
# -----------------------------------------------
# Dois programas de shader distintos:
#
# 1) Shader do SKYBOX:
#    - Vertex: recebe só posição (vec3). Constrói a view SEM translação
#      (coluna 3 zerada) para o cubo sempre rodear a câmera.
#      gl_Position.z = gl_Position.w força o fragmento ao valor máximo
#      de profundidade (z=1 após divisão perspectiva), garantindo que
#      o skybox fique atrás de tudo com GL_LEQUAL.
#    - Fragment: usa samplerCube (não sampler2D), amostrado com vec3.
#
# 2) Shader do OBJETO:
#    - Pipeline normal com transform + view + proj + sampler2D.

def inicializaShaders():
	global Shader_skybox, Shader_objeto

	# ---------------------------------------------------------------
	# 1) SHADER DO SKYBOX  (sem transform, sem UV, profundidade = max)
	# ---------------------------------------------------------------
	vs_skybox = """
		#version 400
		layout(location = 0) in vec3 vertex_posicao;

		uniform mat4 view;
		uniform mat4 proj;

		out vec3 dir_textura;

		void main() {
			dir_textura = vertex_posicao;
			vec4 pos = proj * view * vec4(vertex_posicao, 1.0);
			// Força z = w → profundidade máxima após divisão perspectiva
			gl_Position = pos.xyww;
		}
	"""
	fs_skybox = """
		#version 400
		in vec3 dir_textura;
		uniform samplerCube skybox;
		out vec4 frag_colour;

		void main() {
			frag_colour = texture(skybox, dir_textura);
		}
	"""

	vs = OpenGL.GL.shaders.compileShader(vs_skybox, GL_VERTEX_SHADER)
	fs = OpenGL.GL.shaders.compileShader(fs_skybox, GL_FRAGMENT_SHADER)
	Shader_skybox = OpenGL.GL.shaders.compileProgram(vs, fs)
	glDeleteShader(vs)
	glDeleteShader(fs)

	# ---------------------------------------------------------------
	# 2) SHADER DE OBJETOS
	#    Controle via uniform:  u_modo = 0 → fosco (Phong)
	#                           u_modo = 1 → reflexivo (Environment Mapping)
	# ---------------------------------------------------------------
	vs_objeto = """
		#version 450
		layout(location = 0) in vec3 vertex_posicao;
		layout(location = 1) in vec3 vertex_normal;

		uniform mat4 transform, view, proj;

		out vec3 fragPosWorld;
		out vec3 normalWorld;

		void main() {
			vec4 worldPos = transform * vec4(vertex_posicao, 1.0);
			fragPosWorld  = worldPos.xyz;
			// Corrige a normal para escala não-uniforme
			normalWorld   = mat3(transpose(inverse(transform))) * vertex_normal;
			gl_Position   = proj * view * worldPos;
		}
	"""

	fs_objeto = """
		#version 450
		in vec3 fragPosWorld;
		in vec3 normalWorld;

		// ---- uniforms comuns ----
		uniform vec3 viewPos;
		uniform samplerCube skybox;     // cubemap sempre disponível (usado no modo reflexivo)

		// ---- controle de modo ----
		// 0 = MODO_FOSCO     → Phong clássico
		// 1 = MODO_REFLEXIVO → reflexão pura via cubemap
		uniform int u_modo;

		// ---- uniforms do modo Phong (ignorados no modo reflexivo) ----
		uniform vec3 objectColor;

		out vec4 frag_colour;

		void main() {
			vec3 N = normalize(normalWorld);
			vec3 V = normalize(viewPos - fragPosWorld);

			if (u_modo == 1) {
				// ---- MODO REFLEXIVO ----
				// Reflete o vetor de visão pela normal e amostra o cubemap
				vec3 R = reflect(-V, N);
				frag_colour = texture(skybox, R);

			} else {
				// ---- MODO FOSCO (Phong) ----
				vec3 sunLightDir = normalize(vec3(-1.0, 1.5, -2.0));
				vec3 sunColor    = vec3(1.0, 1.0, 0.9);

				vec3 R = reflect(-sunLightDir, N);

				float Ka        = 0.3;
				float Kd        = 0.7;
				float Ks        = 0.5;
				float shininess = 32.0;

				vec3  ambient  = Ka * sunColor;
				float diff     = max(dot(N, sunLightDir), 0.0);
				vec3  diffuse  = Kd * diff * sunColor;
				float spec     = pow(max(dot(V, R), 0.0), shininess);
				vec3  specular = Ks * spec * sunColor;

				vec3 result = (ambient + diffuse) * objectColor + specular;
				frag_colour = vec4(result, 1.0);
			}
		}
	"""

	vs = OpenGL.GL.shaders.compileShader(vs_objeto, GL_VERTEX_SHADER)
	fs = OpenGL.GL.shaders.compileShader(fs_objeto, GL_FRAGMENT_SHADER)
	Shader_objeto = OpenGL.GL.shaders.compileProgram(vs, fs)
	glDeleteShader(vs)
	glDeleteShader(fs)


# -----------------------------
# Matrizes e Movimentação
# -----------------------------

def calculaFront():
	front = np.array([
		np.cos(np.radians(Cam_yaw)) * np.cos(np.radians(Cam_pitch)),
		np.sin(np.radians(Cam_pitch)),
		np.sin(np.radians(Cam_yaw)) * np.cos(np.radians(Cam_pitch))
	])
	return front / np.linalg.norm(front)

def montaViewMatrix(front, remover_translacao=False):
	"""
	Monta a matriz de visualização.
	Se remover_translacao=True, zera a coluna de translação —
	usado pelo skybox para que ele acompanhe a câmera sem se deslocar.
	"""
	up = np.array([0.0, 1.0, 0.0])
	s  = np.cross(front, up);  s /= np.linalg.norm(s)
	u  = np.cross(s, front)

	view = np.identity(4, dtype=np.float32)
	view[0, :3] =  s
	view[1, :3] =  u
	view[2, :3] = -front

	if not remover_translacao:
		view[0, 3] = -np.dot(s,     Cam_pos)
		view[1, 3] = -np.dot(u,     Cam_pos)
		view[2, 3] =  np.dot(front, Cam_pos)
	# se remover_translacao=True, coluna 3 permanece zero → só rotação

	return view

 
def montaProjecaoMatrix():
	znear, zfar = 0.1, 100.0
	fov     = np.radians(67.0)
	aspecto = WIDTH / HEIGHT

	a = 1 / (np.tan(fov / 2) * aspecto)
	b = 1 /  np.tan(fov / 2)
	c = (zfar + znear) / (znear - zfar)
	d = (2 * znear * zfar) / (znear - zfar)

	return np.array([
		[a, 0,  0, 0],
		[0, b,  0, 0],
		[0, 0,  c, d],
		[0, 0, -1, 0]
	], dtype=np.float32)

# -----------------------------
# Transformação de modelo
# -----------------------------

def transformacaoGenerica(shader, Tx, Ty, Tz, Sx, Sy, Sz, Rx, Ry, Rz):
	translacao = np.array([
		[1, 0, 0, Tx],
		[0, 1, 0, Ty],
		[0, 0, 1, Tz],
		[0, 0, 0,  1]
	], dtype=np.float32)

	rx, ry, rz = np.radians([Rx, Ry, Rz])

	rotX = np.array([
		[1,           0,            0, 0],
		[0, np.cos(rx), -np.sin(rx), 0],
		[0, np.sin(rx),  np.cos(rx), 0],
		[0,           0,            0, 1]
	], dtype=np.float32)

	rotY = np.array([
		[ np.cos(ry), 0, np.sin(ry), 0],
		[          0, 1,          0, 0],
		[-np.sin(ry), 0, np.cos(ry), 0],
		[          0, 0,          0, 1]
	], dtype=np.float32)

	rotZ = np.array([
		[np.cos(rz), -np.sin(rz), 0, 0],
		[np.sin(rz),  np.cos(rz), 0, 0],
		[         0,           0, 1, 0],
		[         0,           0, 0, 1]
	], dtype=np.float32)

	escala = np.array([
		[Sx,  0,  0, 0],
		[ 0, Sy,  0, 0],
		[ 0,  0, Sz, 0],
		[ 0,  0,  0, 1]
	], dtype=np.float32)

	transform = translacao @ rotZ @ rotY @ rotX @ escala
	loc = glGetUniformLocation(shader, "transform")
	glUniformMatrix4fv(loc, 1, GL_TRUE, transform)

# -----------------------------
# Teclado
# -----------------------------

def trataTeclado():
	global Cam_pos

	velocidade = Cam_speed * Tempo_entre_frames
	frente  = calculaFront()
	direita = np.cross(frente, np.array([0.0, 1.0, 0.0]))
	direita /= np.linalg.norm(direita)

	if glfw.get_key(Window, glfw.KEY_W) == glfw.PRESS:
		Cam_pos += frente  * velocidade
	if glfw.get_key(Window, glfw.KEY_S) == glfw.PRESS:
		Cam_pos -= frente  * velocidade
	if glfw.get_key(Window, glfw.KEY_A) == glfw.PRESS:
		Cam_pos -= direita * velocidade
	if glfw.get_key(Window, glfw.KEY_D) == glfw.PRESS:
		Cam_pos += direita * velocidade
	if glfw.get_key(Window, glfw.KEY_ESCAPE) == glfw.PRESS:
		glfw.set_window_should_close(Window, True)

# -----------------------------------------------
# Renderização
# -----------------------------------------------
# ORDEM DE DRAW — crítica para o skybox funcionar:
#
#   1) Desenha os objetos normais primeiro (com depth test normal GL_LESS)
#   2) Muda depth test para GL_LEQUAL
#   3) Desenha o skybox (gl_Position.xyww força z=1 → sempre no fundo)
#   4) Restaura GL_LESS para o próximo frame
#
# Por que GL_LEQUAL e não GL_LESS?
#   O skybox tem profundidade z=1.0 (máxima). O depth buffer é inicializado
#   com 1.0. Com GL_LESS, z=1.0 não passaria (1.0 < 1.0 é falso).
#   Com GL_LEQUAL, 1.0 <= 1.0 é verdadeiro → o skybox é desenhado apenas
#   onde nenhum objeto foi renderizado.

def inicializaRenderizacao():
	global Tempo_entre_frames

	tempo_anterior = glfw.get_time()
	glEnable(GL_DEPTH_TEST)

	proj = montaProjecaoMatrix()

	while not glfw.window_should_close(Window):
		tempo_atual        = glfw.get_time()
		Tempo_entre_frames = tempo_atual - tempo_anterior
		tempo_anterior     = tempo_atual

		glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
		glViewport(0, 0, WIDTH, HEIGHT)

		front = calculaFront()

		view_normal = montaViewMatrix(front, remover_translacao=False)
		view_skybox = montaViewMatrix(front, remover_translacao=True)

		# -------------------------------------------------------
		# 1) Objetos da cena — shader unificado
		# -------------------------------------------------------
		glDepthFunc(GL_LESS)
		glUseProgram(Shader_objeto)

		# Uniforms comuns a todos os objetos
		glUniformMatrix4fv(glGetUniformLocation(Shader_objeto, "view"), 1, GL_TRUE, view_normal)
		glUniformMatrix4fv(glGetUniformLocation(Shader_objeto, "proj"), 1, GL_TRUE, proj)
		glUniform3fv(glGetUniformLocation(Shader_objeto, "viewPos"), 1, Cam_pos)

		# O cubemap fica sempre ligado (unidade 0) — usado apenas no modo reflexivo
		glActiveTexture(GL_TEXTURE0)
		glBindTexture(GL_TEXTURE_CUBE_MAP, Textura_cubemap)
		glUniform1i(glGetUniformLocation(Shader_objeto, "skybox"), 0)

		# --- Cone Fosco (Vermelho) ---
		vao_cone, n_indices_cone = Objetos_cenario["cone"]
		glBindVertexArray(vao_cone)
		glUniform1i(glGetUniformLocation(Shader_objeto, "u_modo"), MODO_FOSCO)
		glUniform3f(glGetUniformLocation(Shader_objeto, "objectColor"), 0.8, 0.2, 0.2)
		transformacaoGenerica(Shader_objeto, -2.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0)
		glDrawElements(GL_TRIANGLES, n_indices_cone, GL_UNSIGNED_INT, None)

		# --- Esfera Fosca (Verde) ---
		vao_esfera, n_indices_esfera = Objetos_cenario["esfera"]
		glBindVertexArray(vao_esfera)
		glUniform1i(glGetUniformLocation(Shader_objeto, "u_modo"), MODO_FOSCO)
		glUniform3f(glGetUniformLocation(Shader_objeto, "objectColor"), 0.2, 0.8, 0.2)
		transformacaoGenerica(Shader_objeto, 0.0, 0.0, -2.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0)
		glDrawElements(GL_TRIANGLES, n_indices_esfera, GL_UNSIGNED_INT, None)

		# --- Torus Reflexivo ---
		vao_torus, n_indices_torus = Objetos_cenario["torus"]
		glBindVertexArray(vao_torus)
		glUniform1i(glGetUniformLocation(Shader_objeto, "u_modo"), MODO_REFLEXIVO)
		# objectColor é ignorado no modo reflexivo, mas pode deixar qualquer valor
		transformacaoGenerica(Shader_objeto, 2.0, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0)
		glDrawElements(GL_TRIANGLES, n_indices_torus, GL_UNSIGNED_INT, None)

		# -------------------------------------------------------
		# 2) Skybox — sempre por último
		# -------------------------------------------------------
		glDepthFunc(GL_LEQUAL)
		glUseProgram(Shader_skybox)

		glUniformMatrix4fv(glGetUniformLocation(Shader_skybox, "view"), 1, GL_TRUE, view_skybox)
		glUniformMatrix4fv(glGetUniformLocation(Shader_skybox, "proj"), 1, GL_TRUE, proj)
		glUniform1i(glGetUniformLocation(Shader_skybox, "skybox"), 0)

		glBindVertexArray(Vao_skybox)
		glDrawArrays(GL_TRIANGLES, 0, 36)

		glDepthFunc(GL_LESS)

		glfw.swap_buffers(Window)
		glfw.poll_events()
		trataTeclado()

	glfw.terminate()

# -----------------------------
# Função principal
# -----------------------------

def main():
	inicializaOpenGL()
	
	Objetos_cenario["esfera"] = inicializaSuperficie('esfera')
	Objetos_cenario["torus"]  = inicializaSuperficie('torus')
	Objetos_cenario["cone"]   = inicializaSuperficie('cone')
	
	inicializaSkybox()
	inicializaShaders()
	carregaCubemap(PASTA_SKYBOX)
	inicializaRenderizacao()

if __name__ == "__main__":
	main()