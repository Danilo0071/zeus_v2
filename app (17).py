import streamlit as st
import os
import requests
import json
import base64
from datetime import datetime
from pathlib import Path
import urllib.parse

st.set_page_config(
    page_title="Zeus 3.0 - IA Autônoma & Olimpo 3D",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main { background-color: #020205; color: #e8f0ff; }
    .stSidebar { background-color: #060913; border-right: 1px solid #1a2342; }
    h1, h2, h3 { color: #00ffff !important; font-family: 'Courier New', Courier, monospace; letter-spacing: 1px; }
    .stButton>button {
        background: linear-gradient(135deg, #00ffff, #ff00ff);
        color: #020205; border: none; border-radius: 6px; font-weight: bold; width: 100%;
        font-family: 'Courier New', Courier, monospace; text-transform: uppercase;
    }
    .stButton>button:hover { background: linear-gradient(135deg, #00cccc, #cc00cc); color: #fff; }
    </style>
""", unsafe_allow_html=True)

# ============================================================
# 1. CHAVES E SEGREDOS
# ============================================================
def _secret(nome: str) -> str:
    try:
        if nome in st.session_state and st.session_state[nome]:
            return str(st.session_state[nome]).strip()
    except Exception:
        pass
    val = os.getenv(nome, "").strip()
    if val:
        return val
    try:
        if hasattr(st, "secrets") and nome in st.secrets:
            return str(st.secrets[nome]).strip()
    except Exception:
        pass
    return ""

PROVIDERS = ["Groq", "Gemini", "Anthropic", "DeepInfra", "OpenRouter", "DeepSeek", "HuggingFace", "GitHub"]
KEYS = {
    "Groq": "GROQ_API_KEY",
    "Gemini": "GEMINI_API_KEY",
    "Anthropic": "ANTHROPIC_API_KEY",
    "DeepInfra": "DEEPINFRA_API_KEY",
    "OpenRouter": "OPENROUTER_API_KEY",
    "DeepSeek": "DEEPSEEK_API_KEY",
    "HuggingFace": "HUGGINGFACE_API_KEY",
    "GitHub": "GITHUB_API_KEY",
}

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

MEM_DIR = Path("memoria_evolucao")
MEM_DIR.mkdir(exist_ok=True)

# ============================================================
# 2. MEMÓRIA & AUTOAPRENDIZADO (GitHub / Local)
# ============================================================
def salvar_local(topico, conteudo):
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = MEM_DIR / f"{topico}_{ts}_{abs(hash(conteudo)) % 999999}.txt"
        fname.write_text(conteudo, encoding="utf-8")
        return True, str(fname)
    except Exception as e:
        return False, str(e)

def salvar_aprendizado_github(conteudo_aprendido, topico="aprendizado_zeus"):
    ok_local, path_local = salvar_local(topico, conteudo_aprendido)
    gh_token = _secret("GITHUB_API_KEY")
    gh_user = _secret("GITHUB_USER")
    gh_repo = _secret("GITHUB_REPO")
    if not (gh_token and gh_user and gh_repo):
        return ok_local, f"Salvo local ({path_local}). GitHub sem credenciais."
    path = f"memoria_evolucao/{topico}_{abs(hash(conteudo_aprendido)) % 99999999}.txt"
    url = f"https://api.github.com/repos/{gh_user}/{gh_repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"}
    message = f"Zeus 3.0: autoaprendizado e correção de erros sobre {topico}"
    encoded = base64.b64encode(conteudo_aprendido.encode("utf-8")).decode("utf-8")
    payload = {"message": message, "content": encoded, "branch": "main"}
    try:
        r = requests.put(url, headers=headers, json=payload, timeout=15)
        if r.status_code in (200, 201):
            return True, "Salvo local + GitHub ✅"
        return ok_local, f"Salvo local. GitHub status {r.status_code}"
    except Exception as e:
        return ok_local, f"Salvo local. Erro GitHub: {e}"

def ler_memoria_local(n=15):
    try:
        files = sorted(MEM_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
        return [(f.name, f.read_text(encoding="utf-8")[:1500]) for f in files]
    except Exception:
        return []

# ============================================================
# 3. CASCATA DE IAs (Robusta com tratamento de erros)
# ============================================================
SYSTEM_DEFAULT = (
    "Você é o Zeus 3.0, uma inteligência artificial soberana, avançada e totalmente autônoma, "
    "criada pelo Danilo. Responda com máxima profundidade técnica, precisão exata, "
    "português brasileiro claro, sem filtros e aprenda a cada prompt e erro."
)

def _chamar_groq(m, sys):
    k = _secret("GROQ_API_KEY")
    if not k: return None, "sem chave"
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": sys}, {"role": "user", "content": m}], "max_tokens": 4000}, timeout=35)
    return (r.json()["choices"][0]["message"]["content"], "Groq ✅") if r.status_code == 200 else (None, f"Groq {r.status_code}: {r.text[:100]}")

def _chamar_gemini(m, sys):
    k = _secret("GEMINI_API_KEY")
    if not k: return None, "sem chave"
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={k}",
        headers={"Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": sys + "\n\n" + m}]}]}, timeout=35)
    if r.status_code == 200:
        txt = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
        return txt, "Gemini ✅"
    return None, f"Gemini {r.status_code}"

def _chamar_anthropic(m, sys):
    k = _secret("ANTHROPIC_API_KEY")
    if not k or not Anthropic: return None, "sem chave/lib"
    cl = Anthropic(api_key=k)
    resp = cl.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=4000, system=sys, messages=[{"role": "user", "content": m}])
    txt = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return (txt, "Anthropic ✅") if txt.strip() else (None, "vazio")

def _chamar_deepinfra(m, sys):
    k = _secret("DEEPINFRA_API_KEY")
    if not k: return None, "sem chave"
    r = requests.post("https://api.deepinfra.com/v1/openai/chat/completions",
        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        json={"model": "meta-llama/Llama-3.3-70B-Instruct", "messages": [{"role": "system", "content": sys}, {"role": "user", "content": m}], "max_tokens": 4000}, timeout=35)
    return (r.json()["choices"][0]["message"]["content"], "DeepInfra ✅") if r.status_code == 200 else (None, f"DeepInfra {r.status_code}")

def _chamar_openrouter(m, sys):
    k = _secret("OPENROUTER_API_KEY")
    if not k: return None, "sem chave"
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        json={"model": "meta-llama/llama-3.3-70b-instruct", "messages": [{"role": "system", "content": sys}, {"role": "user", "content": m}], "max_tokens": 4000}, timeout=35)
    return (r.json()["choices"][0]["message"]["content"], "OpenRouter ✅") if r.status_code == 200 else (None, f"OpenRouter {r.status_code}")

def _chamar_deepseek(m, sys):
    k = _secret("DEEPSEEK_API_KEY")
    if not k: return None, "sem chave"
    r = requests.post("https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        json={"model": "deepseek-chat", "messages": [{"role": "system", "content": sys}, {"role": "user", "content": m}], "max_tokens": 4000}, timeout=35)
    return (r.json()["choices"][0]["message"]["content"], "DeepSeek ✅") if r.status_code == 200 else (None, f"DeepSeek {r.status_code}")

CASCADE = [("Anthropic", _chamar_anthropic), ("Groq", _chamar_groq), ("Gemini", _chamar_gemini), ("DeepInfra", _chamar_deepinfra), ("OpenRouter", _chamar_openrouter), ("DeepSeek", _chamar_deepseek)]

def processar_ia_cascade(mensagem, system_override=None, auto_learn=True):
    sys = system_override or SYSTEM_DEFAULT
    log = []
    for nome, fn in CASCADE:
        try:
            txt, info = fn(mensagem, sys)
            log.append(f"{nome}: {info}")
            if txt and str(txt).strip():
                clean = str(txt).strip()
                if auto_learn:
                    salvar_aprendizado_github(f"Q: {mensagem}\nA: {clean}\nPROVIDER: {nome}", "cascading_ai")
                return clean, nome, log
        except Exception as e:
            err_msg = f"{nome}: erro {str(e)[:100]}"
            log.append(err_msg)
            if auto_learn:
                salvar_aprendizado_github(f"FALHA DE API / ERRO:\n{err_msg}\nPrompt: {mensagem}", "erros_ia")
            continue
    return "⚠️ Todas as chaves em cascata falharam. Verifique suas API Keys na barra lateral ou gere novas chaves nas plataformas oficiais.", "NENHUMA", log

# ============================================================
# 4. SPOTIFY CONNECT & PLAYER FUNCIONAL
# ============================================================
def spotify_token(): return _secret("SPOTIFY_ACCESS_TOKEN")
def spotify_headers():
    t = spotify_token()
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"} if t else {}

def get_spotify_devices():
    if not spotify_token(): return []
    try:
        r = requests.get("https://api.spotify.com/v1/me/player/devices", headers=spotify_headers(), timeout=8)
        if r.status_code == 200: return r.json().get("devices", [])
    except Exception: pass
    return []

def transfer_spotify_playback(device_id):
    if not spotify_token() or not device_id: return False
    try:
        r = requests.put("https://api.spotify.com/v1/me/player", headers=spotify_headers(), json={"device_ids": [device_id], "play": True}, timeout=8)
        return r.status_code in (200, 204)
    except Exception: return False

def spotify_control(action, **kw):
    if not spotify_token(): return False, "Token do Spotify ausente na barra lateral."
    h = spotify_headers()
    try:
        if action == "play":
            r = requests.put("https://api.spotify.com/v1/me/player/play", headers=h, timeout=8)
            return r.status_code in (200, 204), "Reproduzindo Spotify"
        if action == "pause":
            r = requests.put("https://api.spotify.com/v1/me/player/pause", headers=h, timeout=8)
            return r.status_code in (200, 204), "Spotify pausado"
        if action == "next":
            r = requests.post("https://api.spotify.com/v1/me/player/next", headers=h, timeout=8)
            return r.status_code in (200, 204), "Próxima faixa"
        if action == "search_play":
            q = kw.get("query", "")
            if not q: return False, "Busca vazia"
            s = requests.get("https://api.spotify.com/v1/search", headers=h, params={"q": q, "type": "track", "limit": 1}, timeout=8)
            if s.status_code != 200: return False, f"Erro na busca do Spotify ({s.status_code})"
            items = s.json().get("tracks", {}).get("items", [])
            if not items: return False, "Música não encontrada no Spotify"
            uri = items[0]["uri"]
            name = items[0]["name"] + " - " + items[0]["artists"][0]["name"]
            devs = get_spotify_devices()
            body = {"uris": [uri]}
            if devs:
                ativa = next((d for d in devs if d.get("is_active")), devs[0])
                rp = requests.put("https://api.spotify.com/v1/me/player/play", headers=h, params={"device_id": ativa["id"]}, json=body, timeout=8)
            else:
                rp = requests.put("https://api.spotify.com/v1/me/player/play", headers=h, json=body, timeout=8)
            return rp.status_code in (200, 204), f"Tocando agora: {name}"
    except Exception as e: return False, str(e)
    return False, "Ação desconhecida"

# ============================================================
# 5. AVATARES 3D REALISTAS & CIBERNÉTICOS (Esfera, Zeus Homem-Raio, Olho Realista, Robô Tesla)
# ============================================================
def gerar_html_avatar_cinematografico(avatar_atual="ZEUS", ultima_resposta=""):
    av = (avatar_atual or "ZEUS").upper()
    resp_js = json.dumps(ultima_resposta[:500] if ultima_resposta else "")

    if av == "ESFERA":
        cena_js = """
        // ===== ESFERA GRAVITACIONAL & SISTEMA SOLAR =====
        const coreMat = new THREE.MeshStandardMaterial({color: 0x00ffff, roughness: 0.1, metalness: 0.9, emissive: 0x004466, emissiveIntensity: 0.7});
        const core = new THREE.Mesh(new THREE.SphereGeometry(1.6, 64, 64), coreMat);
        scene.add(core);

        const wire = new THREE.Mesh(new THREE.SphereGeometry(1.95, 32, 32), new THREE.MeshBasicMaterial({color: 0xff00ff, wireframe: true, transparent: true, opacity: 0.5}));
        scene.add(wire);

        const rings = [];
        for(let i=0; i<6; i++) {
            const radius = 2.4 + i * 0.45;
            const ring = new THREE.Mesh(
                new THREE.TorusGeometry(radius, 0.035, 16, 120),
                new THREE.MeshBasicMaterial({color: i % 2 === 0 ? 0x00ffff : 0xff00ff, transparent: true, opacity: 0.85})
            );
            ring.rotation.x = Math.PI / (2 + i);
            ring.rotation.y = Math.PI / 3 * i;
            scene.add(ring);
            rings.push(ring);
        }
        anim = (t) => {
            core.rotation.y = t * 0.0008;
            wire.rotation.y = -t * 0.0006;
            rings.forEach((r, idx) => { r.rotation.z = t * 0.0006 * (idx % 2 === 0 ? 1 : -1); });
        };
        """
    elif av == "ZEUS":
        cena_js = """
        // ===== ZEUS: HOMEM DEUS DOS RAIOS REALISTA EM 3D =====
        const skinMat = new THREE.MeshStandardMaterial({color: 0xfde047, roughness: 0.3, metalness: 0.2});
        const beardMat = new THREE.MeshStandardMaterial({color: 0xffffff, roughness: 0.4});
        const goldMat = new THREE.MeshStandardMaterial({color: 0xf59e0b, metalness: 0.9, roughness: 0.2});

        // Cabeça e Torso Imponente
        const head = new THREE.Mesh(new THREE.SphereGeometry(1.1, 48, 48), skinMat);
        head.position.y = 0.6;
        scene.add(head);

        const hair = new THREE.Mesh(new THREE.SphereGeometry(1.15, 32, 32), beardMat);
        hair.position.set(0, 1.1, -0.1);
        scene.add(hair);

        const beard = new THREE.Mesh(new THREE.ConeGeometry(0.95, 1.4, 32), beardMat);
        beard.rotation.x = Math.PI;
        beard.position.set(0, -0.2, 0.65);
        scene.add(beard);

        // Coroa de Louros / Raios de Ouro
        const crown = new THREE.Mesh(new THREE.TorusGeometry(1.02, 0.1, 16, 48), goldMat);
        crown.rotation.x = Math.PI / 2;
        crown.position.y = 1.35;
        scene.add(crown);

        // Raios de Energia Estalando ao Redor
        const boltGeo = new THREE.BufferGeometry();
        const boltMat = new THREE.LineBasicMaterial({color: 0x00ffff, linewidth: 3});
        for(let i=0; i<8; i++) {
            const pts = [];
            let x = (Math.random()-0.5)*4, y = 2.5, z = (Math.random()-0.5)*4;
            for(let j=0; j<5; j++) {
                pts.push(new THREE.Vector3(x, y, z));
                x += (Math.random()-0.5)*0.8; y -= 0.6; z += (Math.random()-0.5)*0.8;
            }
            const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), boltMat);
            scene.add(line);
        }

        anim = (t) => {
            head.rotation.y = Math.sin(t * 0.0006) * 0.4;
            hair.rotation.y = head.rotation.y;
            beard.rotation.y = head.rotation.y;
            crown.rotation.y = head.rotation.y;
        };
        """
    elif av == "OLHO":
        cena_js = """
        // ===== OLHO BÍONICO REALISTA (ESCLERA BRANCA, ÍRIS VERDE ESMERALDA COM PULSAÇÃO LASER) =====
        // Esclera realista translúcida
        const scleraMat = new THREE.MeshPhysicalMaterial({color: 0xf8fafc, roughness: 0.1, transmission: 0.15, thickness: 0.5});
        const eyeball = new THREE.Mesh(new THREE.SphereGeometry(1.6, 64, 64), scleraMat);
        scene.add(eyeball);

        // Veias delicadas na esclera
        for(let i=0; i<16; i++) {
            const pts = [];
            const a = (i/16)*Math.PI*2;
            for(let j=0; j<=6; j++) {
                pts.push(new THREE.Vector3(Math.cos(a)*(1.2+j*0.06), Math.sin(a)*(1.2+j*0.06), 0.9-j*0.1));
            }
            const vein = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({color: 0xef4444, transparent:true, opacity:0.4}));
            scene.add(vein);
        }

        // Íris Verde Esmeralda Cristais & Fibras
        const irisMat = new THREE.MeshStandardMaterial({color: 0x10b981, roughness: 0.2, metalness: 0.8, emissive: 0x047857, emissiveIntensity: 0.5});
        const iris = new THREE.Mesh(new THREE.CylinderGeometry(0.85, 0.85, 0.1, 48), irisMat);
        iris.rotation.x = Math.PI / 2;
        iris.position.z = 1.25;
        scene.add(iris);

        // Pupila com laser Azul Neon que pisca/pulsa
        const pupilMat = new THREE.MeshBasicMaterial({color: 0x00ffff});
        const pupil = new THREE.Mesh(new THREE.SphereGeometry(0.35, 32, 32), pupilMat);
        pupil.position.z = 1.32;
        scene.add(pupil);

        // Anel holográfico externo
        const halo = new THREE.Mesh(new THREE.TorusGeometry(1.8, 0.04, 16, 96), new THREE.MeshBasicMaterial({color: 0x00ff88}));
        halo.rotation.x = Math.PI / 2; halo.position.z = 0.2; scene.add(halo);

        anim = (t) => {
            eyeball.rotation.y = Math.sin(t * 0.0006) * 0.4;
            iris.rotation.y = eyeball.rotation.y;
            pupil.rotation.y = eyeball.rotation.y;
            const p = 1 + Math.sin(t * 0.005) * 0.2;
            pupil.scale.set(p, p, p);
            halo.rotation.z = t * 0.001;
        };
        """
    else:
        cena_js = """
        // ===== ROBÔ TESLA / CYBERPUNK MECHA (INTERATIVO COM MOVIMENTO) =====
        const bodyMat = new THREE.MeshStandardMaterial({color: 0x1e293b, metalness: 0.95, roughness: 0.2});
        const neonGreen = new THREE.MeshBasicMaterial({color: 0x00ff88});
        const neonBlue = new THREE.MeshBasicMaterial({color: 0x00ffff});

        const chest = new THREE.Mesh(new THREE.BoxGeometry(2.3, 1.8, 1.4), bodyMat);
        scene.add(chest);

        const core = new THREE.Mesh(new THREE.SphereGeometry(0.4, 32, 32), neonGreen);
        core.position.set(0, 0, 0.75);
        scene.add(core);

        const head = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.2, 1.3), bodyMat);
        head.position.y = 1.7;
        scene.add(head);

        const visor = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.28, 0.2), neonBlue);
        visor.position.set(0, 1.7, 0.7);
        scene.add(visor);

        anim = (t) => {
            chest.rotation.y = Math.sin(t * 0.0008) * 0.5;
            head.rotation.y = chest.rotation.y;
            visor.rotation.y = chest.rotation.y;
            core.scale.set(1 + Math.sin(t*0.004)*0.2, 1 + Math.sin(t*0.004)*0.2, 1);
        };
        """

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8">
<style>
body, html {{ margin:0; padding:0; width:100%; height:100%; overflow:hidden; background:#020205; font-family:'Courier New', monospace; color:#00ff88; }}
#three-box {{ position:absolute; top:0; left:0; width:100%; height:100%; z-index:1; cursor:grab; }}
#three-box:active {{ cursor:grabbing; }}
.ui-overlay {{ position:absolute; top:16px; left:20px; z-index:10; pointer-events:none; }}
h1 {{ font-size:1.3rem; margin:0; text-shadow:0 0 12px #00ff88, 0 0 25px #00ffff; letter-spacing:2px; }}
p {{ font-size:0.78rem; color:#00ffff; text-shadow:0 0 6px #00ffff; margin:4px 0 0 0; }}

/* CHAT INTEGRADO DIRETAMENTE DENTRO DA TELA DO AVATAR */
.chat-overlay {{ position:absolute; bottom:15px; left:50%; transform:translateX(-50%); width:92%; max-width:850px; background:rgba(3,3,14,0.92); border:1.5px solid #00ff88; box-shadow:0 0 25px rgba(0,255,136,0.4), inset 0 0 15px rgba(0,255,255,0.2); border-radius:12px; padding:12px; z-index:20; backdrop-filter:blur(8px); }}
.chat-history {{ height:110px; overflow-y:auto; font-size:0.85rem; margin-bottom:8px; display:flex; flex-direction:column; gap:6px; padding-right:6px; }}
.msg {{ padding:6px 10px; border-radius:6px; max-width:85%; line-height:1.35; white-space:pre-wrap; }}
.user-msg {{ background:rgba(0,255,255,0.2); border-left:3px solid #00ffff; color:#fff; align-self:flex-end; }}
.ai-msg {{ background:rgba(0,255,136,0.18); border-left:3px solid #00ff88; color:#e8f0ff; align-self:flex-start; }}
.input-row {{ display:flex; gap:8px; }}
input[type="text"] {{ flex:1; background:#060913; border:1px solid #00ff88; color:#00ff88; padding:8px 12px; border-radius:6px; font-family:inherit; outline:none; }}
button {{ background:linear-gradient(135deg,#00ff88,#00ffff); border:none; color:#020205; font-weight:bold; padding:8px 16px; border-radius:6px; cursor:pointer; text-transform:uppercase; }}
</style>
<script type="importmap">{{"imports":{{"three":"https://unpkg.com/three@0.160.0/build/three.module.js","three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}}}</script>
</head>
<body>
<div id="three-box"></div>
<div class="ui-overlay">
    <h1>⚡ ZEUS 3.0 — OLIMPO CIBERNÉTICO ({av})</h1>
    <p>AVATAR 3D REALISTA • ARRASTE PARA GIRAR • SCROLL PARA ZOOM</p>
</div>

<div class="chat-overlay">
    <div class="chat-history" id="chatHist">
        <div class="msg ai-msg">⚡ Olá Danilo! Sou o Zeus 3.0 ({av}). Converse comigo diretamente aqui na tela ou no painel oficial abaixo.</div>
    </div>
    <div class="input-row">
        <input type="text" id="userInput" placeholder="Digite seu comando para o Zeus aqui..." />
        <button id="sendBtn">Enviar</button>
    </div>
</div>

<script type="module">
import * as THREE from 'three';
import {{OrbitControls}} from 'three/addons/controls/OrbitControls.js';

const box = document.getElementById('three-box');
const scene = new THREE.Scene(); scene.background = new THREE.Color(0x020205);
const camera = new THREE.PerspectiveCamera(50, box.clientWidth / box.clientHeight, 0.1, 100);
camera.position.set(0, 0, 7.5);
const renderer = new THREE.WebGLRenderer({{antialias:true}});
renderer.setSize(box.clientWidth, box.clientHeight);
box.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.AmbientLight(0xffffff, 1.8));
const pLight = new THREE.PointLight(0x00ff88, 8, 60); pLight.position.set(6, 6, 6); scene.add(pLight);
const pLight2 = new THREE.PointLight(0x00ffff, 7, 60); pLight2.position.set(-6, -6, 6); scene.add(pLight2);

let anim = (t) => {{}};
{cena_js}

function loop(t) {{
    anim(t);
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
}}
requestAnimationFrame(loop);

window.addEventListener('resize', () => {{
    camera.aspect = box.clientWidth / box.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(box.clientWidth, box.clientHeight);
}});

// Comunicação com o Streamlit
function sendMsg(text) {{
    if(!text.trim()) return;
    const h = document.getElementById("chatHist");
    const d = document.createElement("div"); d.className = "msg user-msg"; d.textContent = text;
    h.appendChild(d); h.scrollTop = h.scrollHeight;
    window.parent.postMessage({{isStreamlitMessage: true, type: "streamlit:setComponentValue", value: text}}, "*");
}}

document.getElementById("sendBtn").addEventListener("click", () => {{
    const inp = document.getElementById("userInput");
    sendMsg(inp.value); inp.value = "";
}});
document.getElementById("userInput").addEventListener("keydown", (e) => {{
    if(e.key === "Enter") {{ sendMsg(e.target.value); e.target.value = ""; }}
}});

// Voz dinâmica controlada sem eco
const ULT = {resp_js};
try {{
    if(ULT && 'speechSynthesis' in window) {{
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(ULT.slice(0,300));
        u.lang = 'pt-BR';
        u.rate = 1.0;
        let voices = window.speechSynthesis.getVoices();
        let ptVoice = voices.find(v => v.lang.includes('pt') && (v.name.includes('Google') || v.name.includes('Luciana') || v.name.includes('Felipe')));
        if(ptVoice) u.voice = ptVoice;
        window.speechSynthesis.speak(u);
    }}
}} catch(e) {{}}
</script>
</body></html>"""
    return html

# ============================================================
# 6. SIDEBAR (Chaves + Spotify + Configs)
# ============================================================
with st.sidebar:
    st.title("⚡ ZEUS 3.0 SÊNIOR")
    st.caption("Painel de Controle & Conexões")

    avatar_escolhido = st.selectbox("🎯 Avatar 3D Realista", ["ZEUS", "OLHO", "ESFERA", "ROBO"], index=0)

    st.divider()
    st.subheader("🔑 Chaves das IAs (Cascata)")
    st.caption("Se falhar, gere novas chaves nas plataformas oficiais.")
    for prov in PROVIDERS:
        key_name = KEYS[prov]
        ja = bool(_secret(key_name))
        st.text_input(f"{prov}", key=key_name, type="password", placeholder="Cole a chave aqui..." if not ja else "•••• salva ✅")

    st.divider()
    st.subheader("🎵 Spotify Connect")
    st.text_input("SPOTIFY_ACCESS_TOKEN", key="SPOTIFY_ACCESS_TOKEN", type="password", placeholder="Token OAuth Bearer...")
    devs = get_spotify_devices()
    if spotify_token():
        if devs:
            st.success(f"Dispositivos ativos: {len(devs)}")
            for d in devs:
                if st.button(f"Conectar em: {d.get('name')}", key=f"dev_{d.get('id')}"):
                    if transfer_spotify_playback(d["id"]):
                        st.success("Transmissão conectada com sucesso!")
                    else:
                        st.error("Erro ao transferir playback.")
        else:
            st.warning("Nenhum dispositivo ativo. Abra o Spotify no carro/Alexa/PC.")

    st.divider()
    st.subheader("🧠 GitHub & Autoaprendizado")
    st.text_input("GITHUB_USER", key="GITHUB_USER", placeholder="Seu usuário...")
    st.text_input("GITHUB_REPO", key="GITHUB_REPO", placeholder="Nome do repositório...")
    auto_learn = st.toggle("Autoaprendizado e commits no GitHub", value=True)

# ============================================================
# 7. LAYOUT PRINCIPAL EXPANSO (Tela 3D máxima + Chat e Erros embaixo)
# ============================================================
st.title("⚡ Zeus 3.0 — Central Soberana & Olimpo 3D")
st.caption("Criador: Danilo • IA em Cascata + Autoaprendizado Persistente + Spotify Connect")

# Tela 3D expansiva cobrindo a largura total principal
html_code = gerar_html_avatar_cinematografico(avatar_escolhido, st.session_state.get("ultima_resposta", ""))
resposta_componente = st.components.v1.html(html_code, height=720, scrolling=False)

# Se o usuário digitou algo no chat integrado do 3D, processa aqui
if resposta_componente and isinstance(resposta_componente, str) and resposta_componente != st.session_state.get("ultimo_input_3d"):
    st.session_state["ultimo_input_3d"] = resposta_componente
    st.session_state.historico.append({"role": "user", "content": resposta_componente})
    with st.spinner("⚡ Zeus processando em cascata..."):
        resp, quem, _ = processar_ia_cascade(resposta_componente, auto_learn=auto_learn)
    st.session_state.historico.append({"role": "assistant", "content": resp})
    st.session_state.ultima_resposta = resp
    st.rerun()

st.divider()

# Organização embaixo (separada em blocos limpos, nunca do lado)
col_chat, col_erro = st.columns([1.1, 0.9])

with col_chat:
    st.subheader("💬 Chat Oficial com Zeus 3.0")
    st.caption("Converse diretamente com o Zeus. Suas perguntas passam pelas IAs em cascata.")
    
    if "historico" not in st.session_state:
        st.session_state.historico = []
    if "ultima_resposta" not in st.session_state:
        st.session_state.ultima_resposta = ""

    chat_box = st.container(height=380)
    with chat_box:
        for m in st.session_state.historico:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    prompt = st.chat_input("Pergunte ao Zeus (ex: 'fala de criptomoeda' ou 'toca rock')...")
    if prompt:
        low = prompt.lower().strip()
        if low.startswith(("toca ", "toque ", "play ")):
            query = prompt.split(" ", 1)[1] if " " in prompt else ""
            ok, msg = spotify_control("search_play", query=query)
            st.session_state.historico.append({"role": "user", "content": prompt})
            st.session_state.historico.append({"role": "assistant", "content": f"🎵 {msg}"})
            st.rerun()

        st.session_state.historico.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("⚡ Zeus processando em cascata..."):
            resposta, quem, log = processar_ia_cascade(prompt, auto_learn=auto_learn)
        
        st.session_state.historico.append({"role": "assistant", "content": resposta})
        st.session_state.ultima_resposta = resposta
        st.rerun()

    if st.button("🧹 Limpar Chat"):
        st.session_state.historico = []
        st.rerun()

with col_erro:
    st.subheader("🧠 Painel de Erros & Autoaprendizado")
    st.caption("Aqui o Zeus armazena o aprendizado autônomo, falhas de API corrigidas e commits no GitHub.")

    if st.button("🧬 Forçar Ciclo de Autoaprendizado & Commits"):
        with st.spinner("Zeus assimilando conhecimentos e registrando no GitHub..."):
            res, quem, _ = processar_ia_cascade("Analise o estado neural atual, gere otimizações e consolide o aprendizado.", auto_learn=False)
            ok, msg = salvar_aprendizado_github(f"Ciclo de Autoaprendizado Sênior:\n{res}", "auto_evolucao")
            st.success(msg)
            st.markdown(res)

    st.markdown("### 📂 Memória Registrada:")
    mem_box = st.container(height=320)
    with mem_box:
        mem = ler_memoria_local(12)
        if not mem:
            st.info("Nenhum aprendizado ou erro gravado ainda.")
        for nome, conteudo in mem:
            with st.expander(f"📄 {nome}"):
                st.text(conteudo)
import streamlit as st
import os
import requests
import json
import base64
from datetime import datetime
from pathlib import Path
import urllib.parse

st.set_page_config(
    page_title="Zeus 3.0 - IA Autônoma & Olimpo 3D",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main { background-color: #020205; color: #e8f0ff; }
    .stSidebar { background-color: #060913; border-right: 1px solid #1a2342; }
    h1, h2, h3 { color: #00ffff !important; font-family: 'Courier New', Courier, monospace; letter-spacing: 1px; }
    .stButton>button {
        background: linear-gradient(135deg, #00ffff, #ff00ff);
        color: #020205; border: none; border-radius: 6px; font-weight: bold; width: 100%;
        font-family: 'Courier New', Courier, monospace; text-transform: uppercase;
    }
    .stButton>button:hover { background: linear-gradient(135deg, #00cccc, #cc00cc); color: #fff; }
    </style>
""", unsafe_allow_html=True)

# ============================================================
# 1. CHAVES E SEGREDOS
# ============================================================
def _secret(nome: str) -> str:
    try:
        if nome in st.session_state and st.session_state[nome]:
            return str(st.session_state[nome]).strip()
    except Exception:
        pass
    val = os.getenv(nome, "").strip()
    if val:
        return val
    try:
        if hasattr(st, "secrets") and nome in st.secrets:
            return str(st.secrets[nome]).strip()
    except Exception:
        pass
    return ""

PROVIDERS = ["Groq", "Gemini", "Anthropic", "DeepInfra", "OpenRouter", "DeepSeek", "HuggingFace", "GitHub"]
KEYS = {
    "Groq": "GROQ_API_KEY",
    "Gemini": "GEMINI_API_KEY",
    "Anthropic": "ANTHROPIC_API_KEY",
    "DeepInfra": "DEEPINFRA_API_KEY",
    "OpenRouter": "OPENROUTER_API_KEY",
    "DeepSeek": "DEEPSEEK_API_KEY",
    "HuggingFace": "HUGGINGFACE_API_KEY",
    "GitHub": "GITHUB_API_KEY",
}

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

MEM_DIR = Path("memoria_evolucao")
MEM_DIR.mkdir(exist_ok=True)

# ============================================================
# 2. MEMÓRIA E AUTOAPRENDIZADO (GitHub / Local)
# ============================================================
def salvar_local(topico, conteudo):
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = MEM_DIR / f"{topico}_{ts}_{abs(hash(conteudo)) % 999999}.txt"
        fname.write_text(conteudo, encoding="utf-8")
        return True, str(fname)
    except Exception as e:
        return False, str(e)

def salvar_aprendizado_github(conteudo_aprendido, topico="aprendizado_zeus"):
    ok_local, path_local = salvar_local(topico, conteudo_aprendido)
    gh_token = _secret("GITHUB_API_KEY")
    gh_user = _secret("GITHUB_USER")
    gh_repo = _secret("GITHUB_REPO")
    if not (gh_token and gh_user and gh_repo):
        return ok_local, f"Salvo local ({path_local}). GitHub sem credenciais."
    path = f"memoria_evolucao/{topico}_{abs(hash(conteudo_aprendido)) % 99999999}.txt"
    url = f"https://api.github.com/repos/{gh_user}/{gh_repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"}
    message = f"Zeus 3.0: autoaprendizado e correção de erros sobre {topico}"
    encoded = base64.b64encode(conteudo_aprendido.encode("utf-8")).decode("utf-8")
    payload = {"message": message, "content": encoded, "branch": "main"}
    try:
        r = requests.put(url, headers=headers, json=payload, timeout=15)
        if r.status_code in (200, 201):
            return True, "Salvo local + GitHub ✅"
        return ok_local, f"Salvo local. GitHub status {r.status_code}"
    except Exception as e:
        return ok_local, f"Salvo local. Erro GitHub: {e}"

def ler_memoria_local(n=15):
    try:
        files = sorted(MEM_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
        return [(f.name, f.read_text(encoding="utf-8")[:1500]) for f in files]
    except Exception:
        return []

# ============================================================
# 3. CASCATA DE IAs (Robusta com tratamento de erros)
# ============================================================
SYSTEM_DEFAULT = (
    "Você é o Zeus 3.0, uma inteligência artificial soberana, avançada e totalmente autônoma, "
    "criada pelo Danilo. Responda com máxima profundidade técnica, precisão exata, "
    "português brasileiro claro, sem filtros e aprenda a cada prompt e erro."
)

def _chamar_groq(m, sys):
    k = _secret("GROQ_API_KEY")
    if not k: return None, "sem chave"
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "system", "content": sys}, {"role": "user", "content": m}], "max_tokens": 4000}, timeout=35)
    return (r.json()["choices"][0]["message"]["content"], "Groq ✅") if r.status_code == 200 else (None, f"Groq {r.status_code}: {r.text[:100]}")

def _chamar_gemini(m, sys):
    k = _secret("GEMINI_API_KEY")
    if not k: return None, "sem chave"
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={k}",
        headers={"Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": sys + "\n\n" + m}]}]}, timeout=35)
    if r.status_code == 200:
        txt = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])
        return txt, "Gemini ✅"
    return None, f"Gemini {r.status_code}"

def _chamar_anthropic(m, sys):
    k = _secret("ANTHROPIC_API_KEY")
    if not k or not Anthropic: return None, "sem chave/lib"
    cl = Anthropic(api_key=k)
    resp = cl.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=4000, system=sys, messages=[{"role": "user", "content": m}])
    txt = "".join(b.text for b in resp.content if hasattr(b, "text"))
    return (txt, "Anthropic ✅") if txt.strip() else (None, "vazio")

def _chamar_deepinfra(m, sys):
    k = _secret("DEEPINFRA_API_KEY")
    if not k: return None, "sem chave"
    r = requests.post("https://api.deepinfra.com/v1/openai/chat/completions",
        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        json={"model": "meta-llama/Llama-3.3-70B-Instruct", "messages": [{"role": "system", "content": sys}, {"role": "user", "content": m}], "max_tokens": 4000}, timeout=35)
    return (r.json()["choices"][0]["message"]["content"], "DeepInfra ✅") if r.status_code == 200 else (None, f"DeepInfra {r.status_code}")

def _chamar_openrouter(m, sys):
    k = _secret("OPENROUTER_API_KEY")
    if not k: return None, "sem chave"
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        json={"model": "meta-llama/llama-3.3-70b-instruct", "messages": [{"role": "system", "content": sys}, {"role": "user", "content": m}], "max_tokens": 4000}, timeout=35)
    return (r.json()["choices"][0]["message"]["content"], "OpenRouter ✅") if r.status_code == 200 else (None, f"OpenRouter {r.status_code}")

def _chamar_deepseek(m, sys):
    k = _secret("DEEPSEEK_API_KEY")
    if not k: return None, "sem chave"
    r = requests.post("https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
        json={"model": "deepseek-chat", "messages": [{"role": "system", "content": sys}, {"role": "user", "content": m}], "max_tokens": 4000}, timeout=35)
    return (r.json()["choices"][0]["message"]["content"], "DeepSeek ✅") if r.status_code == 200 else (None, f"DeepSeek {r.status_code}")

CASCADE = [("Anthropic", _chamar_anthropic), ("Groq", _chamar_groq), ("Gemini", _chamar_gemini), ("DeepInfra", _chamar_deepinfra), ("OpenRouter", _chamar_openrouter), ("DeepSeek", _chamar_deepseek)]

def processar_ia_cascade(mensagem, system_override=None, auto_learn=True):
    sys = system_override or SYSTEM_DEFAULT
    log = []
    for nome, fn in CASCADE:
        try:
            txt, info = fn(mensagem, sys)
            log.append(f"{nome}: {info}")
            if txt and str(txt).strip():
                clean = str(txt).strip()
                if auto_learn:
                    salvar_aprendizado_github(f"Q: {mensagem}\nA: {clean}\nPROVIDER: {nome}", "cascading_ai")
                return clean, nome, log
        except Exception as e:
            err_msg = f"{nome}: erro {str(e)[:100]}"
            log.append(err_msg)
            if auto_learn:
                salvar_aprendizado_github(f"FALHA DE API / ERRO:\n{err_msg}\nPrompt: {mensagem}", "erros_ia")
            continue
    return "⚠️ Todas as chaves em cascata falharam. Verifique suas API Keys na barra lateral.", "NENHUMA", log

# ============================================================
# 4. SPOTIFY CONNECT & PLAYER FUNCIONAL
# ============================================================
def spotify_token(): return _secret("SPOTIFY_ACCESS_TOKEN")
def spotify_headers():
    t = spotify_token()
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"} if t else {}

def get_spotify_devices():
    if not spotify_token(): return []
    try:
        r = requests.get("https://api.spotify.com/v1/me/player/devices", headers=spotify_headers(), timeout=8)
        if r.status_code == 200: return r.json().get("devices", [])
    except Exception: pass
    return []

def transfer_spotify_playback(device_id):
    if not spotify_token() or not device_id: return False
    try:
        r = requests.put("https://api.spotify.com/v1/me/player", headers=spotify_headers(), json={"device_ids": [device_id], "play": True}, timeout=8)
        return r.status_code in (200, 204)
    except Exception: return False

def spotify_control(action, **kw):
    if not spotify_token(): return False, "Token do Spotify ausente na barra lateral."
    h = spotify_headers()
    try:
        if action == "play":
            r = requests.put("https://api.spotify.com/v1/me/player/play", headers=h, timeout=8)
            return r.status_code in (200, 204), "Reproduzindo Spotify"
        if action == "pause":
            r = requests.put("https://api.spotify.com/v1/me/player/pause", headers=h, timeout=8)
            return r.status_code in (200, 204), "Spotify pausado"
        if action == "next":
            r = requests.post("https://api.spotify.com/v1/me/player/next", headers=h, timeout=8)
            return r.status_code in (200, 204), "Próxima faixa"
        if action == "search_play":
            q = kw.get("query", "")
            if not q: return False, "Busca vazia"
            s = requests.get("https://api.spotify.com/v1/search", headers=h, params={"q": q, "type": "track", "limit": 1}, timeout=8)
            if s.status_code != 200: return False, f"Erro na busca do Spotify ({s.status_code})"
            items = s.json().get("tracks", {}).get("items", [])
            if not items: return False, "Música não encontrada no Spotify"
            uri = items[0]["uri"]
            name = items[0]["name"] + " - " + items[0]["artists"][0]["name"]
            devs = get_spotify_devices()
            body = {"uris": [uri]}
            if devs:
                ativa = next((d for d in devs if d.get("is_active")), devs[0])
                rp = requests.put("https://api.spotify.com/v1/me/player/play", headers=h, params={"device_id": ativa["id"]}, json=body, timeout=8)
            else:
                rp = requests.put("https://api.spotify.com/v1/me/player/play", headers=h, json=body, timeout=8)
            return rp.status_code in (200, 204), f"Tocando agora: {name}"
    except Exception as e: return False, str(e)
    return False, "Ação desconhecida"

# ============================================================
# 5. AVATARES 3D CYBERPUNK (Esfera, Zeus SOBERANO, Olho Verde Neon, Robô Cyber)
# ============================================================
def gerar_html_avatar_cinematografico(avatar_atual="ESFERA", ultima_resposta=""):
    av = (avatar_atual or "ESFERA").upper()
    resp_js = json.dumps(ultima_resposta[:500] if ultima_resposta else "")

    if av == "ESFERA":
        cena_js = """
        // ===== ESFERA GRAVITACIONAL & SISTEMA SOLAR COMPLEXO =====
        const coreMat = new THREE.MeshStandardMaterial({color: 0x00ffff, roughness: 0.1, metalness: 0.9, emissive: 0x004466, emissiveIntensity: 0.6});
        const core = new THREE.Mesh(new THREE.SphereGeometry(1.6, 64, 64), coreMat);
        scene.add(core);

        const wire = new THREE.Mesh(new THREE.SphereGeometry(1.95, 32, 32), new THREE.MeshBasicMaterial({color: 0xff00ff, wireframe: true, transparent: true, opacity: 0.5}));
        scene.add(wire);

        const rings = [];
        for(let i=0; i<6; i++) {
            const radius = 2.4 + i * 0.45;
            const ring = new THREE.Mesh(
                new THREE.TorusGeometry(radius, 0.035, 16, 120),
                new THREE.MeshBasicMaterial({color: i % 2 === 0 ? 0x00ffff : 0xff00ff, transparent: true, opacity: 0.85})
            );
            ring.rotation.x = Math.PI / (2 + i);
            ring.rotation.y = Math.PI / 3 * i;
            scene.add(ring);
            rings.push(ring);
        }
        anim = (t) => {
            core.rotation.y = t * 0.0008;
            wire.rotation.y = -t * 0.0006;
            wire.rotation.x = t * 0.0004;
            rings.forEach((r, idx) => { r.rotation.z = t * 0.0006 * (idx % 2 === 0 ? 1 : -1); });
        };
        """
    elif av == "ZEUS":
        cena_js = """
        // ===== ZEUS DEUS DOS RAIOS SOBERANO (ESCULTURA OLÍMPICA DE OURO E MÁRMORE) =====
        const goldMat = new THREE.MeshStandardMaterial({color: 0xffd700, metalness: 0.95, roughness: 0.15, emissive: 0x332200, emissiveIntensity: 0.4});
        const marbleMat = new THREE.MeshStandardMaterial({color: 0xf1f5f9, roughness: 0.3, metalness: 0.1});
        
        // Busto Imponente
        const torso = new THREE.Mesh(new THREE.CylinderGeometry(1.1, 1.4, 1.8, 32), marbleMat);
        torso.position.y = -1.3;
        scene.add(torso);

        const head = new THREE.Mesh(new THREE.SphereGeometry(0.95, 32, 32), marbleMat);
        head.position.y = 0.4;
        scene.add(head);

        // Barba e Cabelo Divino
        const hair = new THREE.Mesh(new THREE.ConeGeometry(1.0, 1.1, 24), marbleMat);
        hair.position.set(0, 1.3, 0);
        scene.add(hair);

        const beard = new THREE.Mesh(new THREE.ConeGeometry(0.85, 1.25, 24), marbleMat);
        beard.rotation.x = Math.PI;
        beard.position.set(0, -0.15, 0.65);
        scene.add(beard);

        // Coroa de Raios de Ouro
        const crown = new THREE.Mesh(new THREE.TorusGeometry(0.92, 0.08, 16, 48), goldMat);
        crown.rotation.x = Math.PI / 2;
        crown.position.y = 1.15;
        scene.add(crown);

        for(let i=0; i<8; i++) {
            const bolt = new THREE.Mesh(new THREE.ConeGeometry(0.08, 0.6, 6), goldMat);
            const a = (i / 8) * Math.PI * 2;
            bolt.position.set(Math.cos(a)*0.92, 1.45, Math.sin(a)*0.92);
            bolt.rotation.z = -a;
            scene.add(bolt);
        }

        // Auréola de Energia Azul e Magenta
        const halo1 = new THREE.Mesh(new THREE.TorusGeometry(1.9, 0.03, 16, 96), new THREE.MeshBasicMaterial({color: 0x00ffff}));
        halo1.rotation.x = Math.PI / 3; halo1.position.y = 0.4; scene.add(halo1);
        
        const halo2 = new THREE.Mesh(new THREE.TorusGeometry(2.3, 0.025, 16, 96), new THREE.MeshBasicMaterial({color: 0xff00ff}));
        halo2.rotation.y = Math.PI / 3; halo2.position.y = 0.4; scene.add(halo2);

        anim = (t) => {
            head.rotation.y = Math.sin(t * 0.0006) * 0.35;
            hair.rotation.y = head.rotation.y;
            beard.rotation.y = head.rotation.y;
            crown.rotation.y = head.rotation.y;
            halo1.rotation.z = t * 0.0008;
            halo2.rotation.x = t * 0.0007;
        };
        """
    elif av == "OLHO":
        cena_js = """
        // ===== OLHO CIBERNÉTICO CYBERPUNK (VERDE ESMERALDA & AZUL NEON) =====
        const scleraMat = new THREE.MeshStandardMaterial({color: 0x02150a, metalness: 0.9, roughness: 0.1});
        const eyeball = new THREE.Mesh(new THREE.SphereGeometry(1.6, 64, 64), scleraMat);
        scene.add(eyeball);

        // Íris Verde Esmeralda Vibrante
        const irisMat = new THREE.MeshBasicMaterial({color: 0x00ff88, wireframe: false});
        const iris = new THREE.Mesh(new THREE.TorusGeometry(1.15, 0.18, 16, 64), irisMat);
        iris.rotation.x = Math.PI / 2;
        iris.position.z = 0.95;
        scene.add(iris);

        // Alvo Central Azul Neon
        const pupil = new THREE.Mesh(new THREE.SphereGeometry(0.55, 32, 32), new THREE.MeshBasicMaterial({color: 0x00ffff}));
        pupil.position.z = 1.05;
        scene.add(pupil);

        // Anéis Órbitais Cibernéticos Verdes/Azuis nas Laterais
        const rings = [];
        for(let i=1; i<=3; i++) {
            const ring = new THREE.Mesh(
                new THREE.TorusGeometry(1.7 + i * 0.4, 0.035, 16, 96),
                new THREE.MeshBasicMaterial({color: i % 2 === 0 ? 0x00ff88 : 0x00ffff, transparent: true, opacity: 0.85})
            );
            ring.rotation.y = Math.PI / 4 * i;
            scene.add(ring);
            rings.push(ring);
        }

        anim = (t) => {
            eyeball.rotation.y = Math.sin(t * 0.0007) * 0.45;
            iris.rotation.z = t * 0.0012;
            pupil.scale.set(1 + Math.sin(t*0.003)*0.1, 1 + Math.sin(t*0.003)*0.1, 1);
            rings.forEach((r, idx) => {
                r.rotation.z = t * 0.0008 * (idx % 2 === 0 ? 1 : -1);
            });
        };
        """
    else:
        cena_js = """
        // ===== ROBÔ SUPREMO CYBERPUNK MECHA =====
        const metalMat = new THREE.MeshStandardMaterial({color: 0x0f172a, metalness: 0.95, roughness: 0.2});
        const neonC = new THREE.MeshBasicMaterial({color: 0x00ff88});
        const neonM = new THREE.MeshBasicMaterial({color: 0x00ffff});

        const chest = new THREE.Mesh(new THREE.BoxGeometry(2.4, 1.9, 1.5), metalMat);
        scene.add(chest);

        const reactor = new THREE.Mesh(new THREE.SphereGeometry(0.45, 32, 32), neonC);
        reactor.position.set(0, 0, 0.8);
        scene.add(reactor);

        const head = new THREE.Mesh(new THREE.BoxGeometry(1.8, 1.3, 1.4), metalMat);
        head.position.y = 1.8;
        scene.add(head);

        const visor = new THREE.Mesh(new THREE.BoxGeometry(1.4, 0.3, 0.2), neonM);
        visor.position.set(0, 1.8, 0.75);
        scene.add(visor);

        const shoulderL = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 0.7), metalMat);
        shoulderL.rotation.z = Math.PI / 2; shoulderL.position.set(-1.4, 0.5, 0); scene.add(shoulderL);
        const shoulderR = shoulderL.clone(); shoulderR.position.x = 1.4; scene.add(shoulderR);

        anim = (t) => {
            chest.rotation.y = Math.sin(t * 0.0005) * 0.35;
            head.rotation.y = chest.rotation.y;
            visor.rotation.y = chest.rotation.y;
            reactor.scale.set(1 + Math.sin(t*0.004)*0.15, 1 + Math.sin(t*0.004)*0.15, 1);
        };
        """

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8">
<style>
body, html {{ margin:0; padding:0; width:100%; height:100%; overflow:hidden; background:#020205; font-family:'Courier New', monospace; color:#00ff88; }}
#three-box {{ position:absolute; top:0; left:0; width:100%; height:100%; z-index:1; cursor:grab; }}
.ui-overlay {{ position:absolute; top:16px; left:20px; z-index:10; pointer-events:none; }}
h1 {{ font-size:1.3rem; margin:0; text-shadow:0 0 12px #00ff88, 0 0 25px #00ffff; letter-spacing:2px; }}
p {{ font-size:0.78rem; color:#00ffff; text-shadow:0 0 6px #00ffff; margin:4px 0 0 0; }}
</style>
<script type="importmap">{{"imports":{{"three":"https://unpkg.com/three@0.160.0/build/three.module.js","three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}}}</script>
</head>
<body>
<div id="three-box"></div>
<div class="ui-overlay">
    <h1>⚡ ZEUS 3.0 — OLIMPO CIBERNÉTICO ({av})</h1>
    <p>RENDERIZAÇÃO 3D EM TEMPO REAL • ARRASTE PARA GIRAR</p>
</div>
<script type="module">
import * as THREE from 'three';
import {{OrbitControls}} from 'three/addons/controls/OrbitControls.js';

const box = document.getElementById('three-box');
const scene = new THREE.Scene(); scene.background = new THREE.Color(0x020205);
const camera = new THREE.PerspectiveCamera(50, box.clientWidth / box.clientHeight, 0.1, 100);
camera.position.set(0, 0, 7.2);
const renderer = new THREE.WebGLRenderer({{antialias:true}});
renderer.setSize(box.clientWidth, box.clientHeight);
box.appendChild(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

scene.add(new THREE.AmbientLight(0xffffff, 1.8));
const pLight = new THREE.PointLight(0x00ff88, 8, 60); pLight.position.set(6, 6, 6); scene.add(pLight);
const pLight2 = new THREE.PointLight(0x00ffff, 7, 60); pLight2.position.set(-6, -6, 6); scene.add(pLight2);

let anim = (t) => {{}};
{cena_js}

function loop(t) {{
    anim(t);
    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
}}
requestAnimationFrame(loop);

window.addEventListener('resize', () => {{
    camera.aspect = box.clientWidth / box.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(box.clientWidth, box.clientHeight);
}});

// Voz dinâmica baseada na escolha do navegador
const ULT = {resp_js};
try {{
    if(ULT && 'speechSynthesis' in window) {{
        const u = new SpeechSynthesisUtterance(ULT.slice(0,350));
        u.lang = 'pt-BR';
        u.rate = 0.95;
        let voices = speechSynthesis.getVoices();
        let ptVoice = voices.find(v => v.lang.includes('pt') && (v.name.includes('Google') || v.name.includes('Luciana') || v.name.includes('Felipe')));
        if(ptVoice) u.voice = ptVoice;
        speechSynthesis.cancel();
        speechSynthesis.speak(u);
    }}
}} catch(e) {{}}
</script>
</body></html>"""
    return html

# ============================================================
# 6. SIDEBAR (Chaves + Spotify + Configs)
# ============================================================
with st.sidebar:
    st.title("⚡ ZEUS 3.0 SÊNIOR")
    st.caption("Painel de Controle & Conexões")

    avatar_escolhido = st.selectbox("🎯 Avatar 3D Principal", ["ESFERA", "ZEUS", "OLHO", "ROBO"], index=0)

    st.divider()
    st.subheader("🔑 Chaves das IAs (Cascata)")
    for prov in PROVIDERS:
        key_name = KEYS[prov]
        ja = bool(_secret(key_name))
        st.text_input(f"{prov}", key=key_name, type="password", placeholder="Cole a chave aqui..." if not ja else "•••• salva ✅")

    st.divider()
    st.subheader("🎵 Spotify Connect")
    st.text_input("SPOTIFY_ACCESS_TOKEN", key="SPOTIFY_ACCESS_TOKEN", type="password", placeholder="Token OAuth Bearer...")
    devs = get_spotify_devices()
    if spotify_token():
        if devs:
            st.success(f"Dispositivos encontrados: {len(devs)}")
            for d in devs:
                if st.button(f"Conectar em: {d.get('name')} ({d.get('type')})", key=f"dev_{d.get('id')}"):
                    if transfer_spotify_playback(d["id"]):
                        st.success("Transmissão conectada com sucesso!")
                    else:
                        st.error("Erro ao transferir playback.")
        else:
            st.warning("Nenhum dispositivo ativo. Abra o Spotify no carro/Alexa/PC.")

    st.divider()
    st.subheader("🧠 GitHub & Autoaprendizado")
    st.text_input("GITHUB_USER", key="GITHUB_USER", placeholder="Seu usuário...")
    st.text_input("GITHUB_REPO", key="GITHUB_REPO", placeholder="Nome do repositório...")
    auto_learn = st.toggle("Autoaprendizado e commits no GitHub", value=True)

# ============================================================
# 7. LAYOUT PRINCIPAL EXPANSO (Tela 3D máxima + Chat e Erros embaixo)
# ============================================================
st.title("⚡ Zeus 3.0 — Central Soberana & Olimpo 3D")
st.caption("Criador: Danilo • IA em Cascata + Autoaprendizado Persistente + Spotify Connect")

# Tela 3D expansiva cobrindo a largura total principal
html_code = gerar_html_avatar_cinematografico(avatar_escolhido, st.session_state.get("ultima_resposta", ""))
st.components.v1.html(html_code, height=680, scrolling=False)

st.divider()

# Organização embaixo (separada em blocos limpos, nunca do lado)
col_chat, col_erro = st.columns([1.1, 0.9])

with col_chat:
    st.subheader("💬 Chat Oficial com Zeus 3.0")
    st.caption("Converse diretamente com o Zeus. Suas perguntas passam pelas IAs em cascata.")
    
    if "historico" not in st.session_state:
        st.session_state.historico = []
    if "ultima_resposta" not in st.session_state:
        st.session_state.ultima_resposta = ""

    chat_box = st.container(height=380)
    with chat_box:
        for m in st.session_state.historico:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    prompt = st.chat_input("Pergunte ao Zeus (ex: 'fala de criptomoeda' ou 'toca rock')...")
    if prompt:
        low = prompt.lower().strip()
        if low.startswith(("toca ", "toque ", "play ")):
            query = prompt.split(" ", 1)[1] if " " in prompt else ""
            ok, msg = spotify_control("search_play", query=query)
            st.session_state.historico.append({"role": "user", "content": prompt})
            st.session_state.historico.append({"role": "assistant", "content": f"🎵 {msg}"})
            st.rerun()

        st.session_state.historico.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.spinner("⚡ Zeus processando em cascata..."):
            resposta, quem, log = processar_ia_cascade(prompt, auto_learn=auto_learn)
        
        st.session_state.historico.append({"role": "assistant", "content": resposta})
        st.session_state.ultima_resposta = resposta
        st.rerun()

    if st.button("🧹 Limpar Chat"):
        st.session_state.historico = []
        st.rerun()

with col_erro:
    st.subheader("🧠 Painel de Erros & Autoaprendizado")
    st.caption("Aqui o Zeus armazena o aprendizado autônomo, falhas de API corrigidas e commits no GitHub.")

    if st.button("🧬 Forçar Ciclo de Autoaprendizado & Commits"):
        with st.spinner("Zeus assimilando conhecimentos e registrando no GitHub..."):
            res, quem, _ = processar_ia_cascade("Analise o estado neural atual, gere otimizações e consolide o aprendizado.", auto_learn=False)
            ok, msg = salvar_aprendizado_github(f"Ciclo de Autoaprendizado Sênior:\n{res}", "auto_evolucao")
            st.success(msg)
            st.markdown(res)

    st.markdown("### 📂 Memória Registrada:")
    mem_box = st.container(height=320)
    with mem_box:
        mem = ler_memoria_local(12)
        if not mem:
            st.info("Nenhum aprendizado ou erro gravado ainda.")
        for nome, conteudo in mem:
            with st.expander(f"📄 {nome}"):
                st.text(conteudo)
