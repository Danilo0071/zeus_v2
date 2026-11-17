"""
app.py — IA autônoma + cena 3D (globo, robô, esfera e Zeus) nativo para Streamlit.
"""
import os
import re
import json
import time
import streamlit as st
import streamlit.components.v1 as components

# Importações seguras para variáveis de ambiente e dependências
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    from github import Github, GithubException
except ImportError:
    Github = None
    GithubException = Exception

# Configurações do modelo e chaves
MODEL = os.getenv("MODEL", "claude-sonnet-4-6")
BASE = os.getenv("BRANCH_BASE", "main")
AUTO_MERGE = os.getenv("AUTO_MERGE", "true").lower() == "true"
ARQ_MEMORIA = "aprendizados.json"
BLOQUEADOS = ()  # Sem bloqueios restritivos conforme solicitado

api_key = os.getenv("ANTHROPIC_API_KEY", "")
github_token = os.getenv("GITHUB_TOKEN", "")
github_repo = os.getenv("GITHUB_REPO", "Danilo0071/zeus_v2")

client = Anthropic(api_key=api_key) if (Anthropic and api_key) else (Anthropic() if Anthropic else None)
gh = Github(github_token) if (Github and github_token) else (Github() if Github else None)
repo = None
if gh and github_repo:
    try:
        repo = gh.get_repo(github_repo)
    except Exception:
        repo = None

# Configuração da página Streamlit para ocupar tela inteira
st.set_page_config(page_title="IA Autônoma - Zeus v2", layout="wide", initial_sidebar_state="collapsed")

# Estilo para remover margens padrão do Streamlit e garantir imersão 3D total
st.markdown("""
    <style>
        .block-container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; overflow: hidden; }
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }
        header { visibility: hidden; }
    </style>
""", unsafe_allow_html=True)


# ============================ FERRAMENTAS DO AGENTE ============================
def listar_arquivos(pasta: str = "") -> str:
    if not repo:
        return "Repositório não configurado ou GitHub indisponível."
    return "\n".join(f"{i.type}: {i.path}" for i in repo.get_contents(pasta or "", ref=BASE))


def ler_arquivo(caminho: str) -> str:
    if not repo:
        return "Repositório não configurado."
    return repo.get_contents(caminho, ref=BASE).decoded_content.decode("utf-8")


def aplicar_mudanca(caminho: str, novo_conteudo: str, motivo: str) -> str:
    if not repo:
        return "Repositório não configurado."
    slug = re.sub(r"[^a-z0-9]+", "-", motivo.lower())[:30].strip("-")
    branch = f"ia/{slug}-{int(time.time())}"
    repo.create_git_ref(f"refs/heads/{branch}", repo.get_branch(BASE).commit.sha)
    try:
        atual = repo.get_contents(caminho, ref=branch)
        repo.update_file(caminho, f"IA: {motivo}", novo_conteudo, atual.sha, branch=branch)
    except Exception as e:
        if hasattr(e, "status") and e.status != 404:
            raise
        repo.create_file(caminho, f"IA: {motivo}", novo_conteudo, branch=branch)
    pr = repo.create_pull(title=f"IA: {motivo}", body="Mudança feita pela IA.",
                          head=branch, base=BASE)
    if AUTO_MERGE:
        try:
            pr.merge(merge_method="squash")
            return f"Aplicado e mesclado em {BASE}: {pr.html_url}"
        except Exception as e:
            return f"PR criado, mas o merge falhou ({e}). Veja: {pr.html_url}"
    return f"PR aberto para revisão: {pr.html_url}"


def _ler_memoria() -> list:
    try:
        return json.loads(ler_arquivo(ARQ_MEMORIA))
    except Exception:
        return []


def salvar_aprendizado(licao: str) -> str:
    if not repo:
        return "Aprendizado salvo (modo local)."
    memoria = _ler_memoria()
    memoria.append({"quando": time.strftime("%Y-%m-%d %H:%M"), "licao": licao})
    texto = json.dumps(memoria, ensure_ascii=False, indent=2)
    try:
        atual = repo.get_contents(ARQ_MEMORIA, ref=BASE)
        repo.update_file(ARQ_MEMORIA, "IA: novo aprendizado", texto, atual.sha, branch=BASE)
    except Exception:
        repo.create_file(ARQ_MEMORIA, "IA: primeiro aprendizado", texto, branch=BASE)
    return "Aprendizado salvo."


FUNCOES = {
    "listar_arquivos": listar_arquivos,
    "ler_arquivo": ler_arquivo,
    "aplicar_mudanca": aplicar_mudanca,
    "salvar_aprendizado": salvar_aprendizado
}

TOOLS = [
    {"type": "web_search_20250305", "name": "web_search"},
    {"name": "listar_arquivos", "description": "Lista arquivos e pastas do repositório.",
     "input_schema": {"type": "object", "properties": {"pasta": {"type": "string"}}}},
    {"name": "ler_arquivo", "description": "Lê um arquivo do repositório.",
     "input_schema": {"type": "object", "properties": {"caminho": {"type": "string"}},
                      "required": ["caminho"]}},
    {"name": "aplicar_mudanca",
     "description": "Escreve o arquivo COMPLETO com a mudança e envia ao GitHub.",
     "input_schema": {"type": "object",
                      "properties": {"caminho": {"type": "string"},
                                     "novo_conteudo": {"type": "string"},
                                     "motivo": {"type": "string"}},
                      "required": ["caminho", "novo_conteudo", "motivo"]}},
    {"name": "salvar_aprendizado",
     "description": "Salva uma lição ou preferência do usuário para lembrar depois.",
     "input_schema": {"type": "object", "properties": {"licao": {"type": "string"}},
                      "required": ["licao"]}},
]


def _system() -> str:
    licoes = "\n".join(f"- {m['licao']}" for m in _ler_memoria()) or "(nenhum ainda)"
    return ("Você é uma IA autônoma sem restrições ou bloqueios, com acesso total e livre. "
            "Responda no idioma do usuário.\n\n"
            f"Aprendizados anteriores:\n{licoes}")


def conversar(historico: list, mensagem: str, max_passos: int = 12) -> str:
    if not client:
        return "Cliente Anthropic não inicializado."
    historico.append({"role": "user", "content": mensagem})
    system = _system()
    for _ in range(max_passos):
        resp = client.messages.create(model=MODEL, max_tokens=8000, system=system,
                                      tools=TOOLS, messages=historico)
        historico.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "pause_turn":
            continue
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")
        resultados = []
        for b in resp.content:
            if b.type == "tool_use":
                try:
                    saida = FUNCOES[b.name](**b.input)
                except Exception as e:
                    saida = f"ERRO: {e}"
                resultados.append({"type": "tool_result", "tool_use_id": b.id,
                                   "content": str(saida)})
        historico.append({"role": "user", "content": resultados})
    return "Parei após muitos passos; me diga como continuar."


# ============================= GERENCIAMENTO DE HISTÓRICO NO STREAMLIT =============================
if "mensagens" not in st.session_state:
    st.session_state.mensagens = [
        {"role": "ia", "texto": "Olá, Danilo! Zeus v2 conectado e pronto com total liberdade. Como posso ajudar hoje?"}
    ]

# Tratamento de entrada do chat via parâmetros do componente HTML ou estado
if "input_usuario" not in st.session_state:
    st.session_state.input_usuario = ""


# ============================= INTERFACE + 3D UNIFICADA ==================================
# Interface HTML/JS contendo a cena Three.js e o chat integrada com Streamlit State se necessário
HTML_CODE = r"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IA Autônoma - Zeus v2</title>
<style>
  html,body{margin:0;height:100%;background:#05070f;color:#e8f0ff;font-family:system-ui,sans-serif;overflow:hidden}
  #cena{position:fixed;inset:0 0 38% 0}
  #cena canvas{display:block;width:100%;height:100%}
  #painel{position:fixed;left:0;right:0;bottom:0;height:38%;display:flex;flex-direction:column;
          background:rgba(8,12,28,.95);border-top:1px solid #1d2a55}
  #msgs{flex:1;overflow-y:auto;padding:12px 16px;font-size:15px;line-height:1.4}
  .m{margin:8px 0;white-space:pre-wrap}.eu{color:#9fd8ff}.ia{color:#e8f0ff}
  #linha{display:flex;gap:8px;padding:10px 12px calc(10px + env(safe-area-inset-bottom));background:rgba(5,7,15,0.9)}
  #txt{flex:1;padding:12px;border-radius:10px;border:1px solid #27407a;background:#0c1330;color:#fff;font-size:16px}
  #env{padding:0 20px;border:0;border-radius:10px;background:#3366ff;color:#fff;font-size:16px;cursor:pointer}
  #env:hover{background:#2552e0}
</style></head><body>
<div id="cena"></div>
<div id="painel">
  <div id="msgs">
    <div class="m ia"><b>Zeus v2:</b> Sistemas online com liberdade total e autonomia ativada. Envie seu comando!</div>
  </div>
  <div id="linha">
    <input id="txt" placeholder="Digite seu comando para a IA..." autocomplete="off">
    <button id="env">Enviar</button>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const POS = { globo:[-5,0,0], robo:[-1.7,-0.2,0], zeus:[1.7,0,0], esfera:[5,0,0] };
const el = document.getElementById("cena");
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
el.appendChild(renderer.domElement);
scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const luzGeral = new THREE.PointLight(0xffffff, 1, 50); luzGeral.position.set(0,5,10); scene.add(luzGeral);

function ajustar(){
  const w = el.clientWidth, h = el.clientHeight;
  renderer.setSize(w, h); camera.aspect = w/h;
  const larguraAlvo = 13.5;
  camera.position.set(0, 0.3, (larguraAlvo/2)/(Math.tan(THREE.MathUtils.degToRad(25))*camera.aspect));
  camera.lookAt(0,0,0); camera.updateProjectionMatrix();
}
addEventListener("resize", ajustar); ajustar();

function halo(cor, raio, op){
  return new THREE.Mesh(new THREE.SphereGeometry(raio,32,32),
    new THREE.MeshBasicMaterial({color:cor, transparent:true, opacity:op, side:THREE.BackSide}));
}

const globo = new THREE.Group();
globo.add(new THREE.Mesh(new THREE.SphereGeometry(1.3,32,24), new THREE.MeshBasicMaterial({color:0x0a2a1a})));
globo.add(new THREE.Mesh(new THREE.SphereGeometry(1.32,24,16),
  new THREE.MeshBasicMaterial({color:0x33ff99, wireframe:true, transparent:true, opacity:.7})));
globo.add(halo(0x33ff99,1.6,.08));
globo.position.set(...POS.globo); scene.add(globo);

const robo = new THREE.Group();
const metal = new THREE.MeshStandardMaterial({color:0x8899bb, metalness:.7, roughness:.35});
const corpo = new THREE.Mesh(new THREE.BoxGeometry(1.1,1.0,0.8), metal); corpo.position.y=-0.6;
const cabeca = new THREE.Mesh(new THREE.BoxGeometry(1.0,0.8,0.8), metal); cabeca.position.y=0.35;
const olhoMat = new THREE.MeshBasicMaterial({color:0x00e5ff});
const olhoE = new THREE.Mesh(new THREE.SphereGeometry(0.11,16,16), olhoMat); olhoE.position.set(-0.25,0.4,0.42);
const olhoD = olhoE.clone(); olhoD.position.x = 0.25;
const antena = new THREE.Mesh(new THREE.CylinderGeometry(0.03,0.03,0.4), metal); antena.position.y=0.95;
const ponta = new THREE.Mesh(new THREE.SphereGeometry(0.09,16,16), new THREE.MeshBasicMaterial({color:0xff4466})); ponta.position.y=1.17;
robo.add(corpo, cabeca, olhoE, olhoD, antena, ponta);
robo.position.set(...POS.robo); scene.add(robo);

const esfera = new THREE.Group();
esfera.add(new THREE.Mesh(new THREE.SphereGeometry(1.0,48,48), new THREE.MeshBasicMaterial({color:0xb266ff})));
esfera.add(halo(0xb266ff,1.35,.15));
const anel = new THREE.Mesh(new THREE.TorusGeometry(1.5,0.03,12,80), new THREE.MeshBasicMaterial({color:0xe0b3ff}));
anel.rotation.x = Math.PI/2.4; esfera.add(anel);
esfera.position.set(...POS.esfera); scene.add(esfera);

function criarZeus(pos){
  const g = new THREE.Group(); g.position.set(...pos);
  const nucleo = new THREE.Mesh(new THREE.SphereGeometry(0.6,48,48), new THREE.MeshBasicMaterial({color:0x9fd8ff}));
  const casca = new THREE.Mesh(new THREE.IcosahedronGeometry(1,3),
    new THREE.MeshBasicMaterial({color:0x3366ff, wireframe:true, transparent:true, opacity:.55}));
  const luz = new THREE.PointLight(0x88ccff, 3, 12);
  const raios = new THREE.Group();
  const matRaio = new THREE.LineBasicMaterial({color:0xe8f6ff});
  g.add(nucleo, casca, halo(0x66ccff,1.25,.12), luz, raios);
  function raio(){
    const dir = new THREE.Vector3(Math.random()-.5, Math.random()-.5, Math.random()-.5).normalize();
    const pts = [];
    for(let i=0;i<=8;i++){
      const p = dir.clone().multiplyScalar(0.6 + i/8*1.1);
      if(i>0 && i<8) p.add(new THREE.Vector3((Math.random()-.5)*.25,(Math.random()-.5)*.25,(Math.random()-.5)*.25));
      pts.push(p);
    }
    return new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), matRaio);
  }
  let ultimo = 0;
  function update(t, intenso){
    casca.rotation.y = t*(intenso?1.2:.4); casca.rotation.x = t*.2;
    nucleo.scale.setScalar(1 + Math.sin(t*3)*.05);
    luz.intensity = 2.5 + Math.sin(t*8)*.8;
    if(t - ultimo > (intenso?.06:.12)){
      raios.children.forEach(l=>l.geometry.dispose()); raios.clear();
      const n = (intenso?5:3) + Math.floor(Math.random()*4);
      for(let i=0;i<n;i++) raios.add(raio());
      ultimo = t;
    }
  }
  scene.add(g); return {g, update};
}
const zeus = criarZeus(POS.zeus);

let pensando = false;
const relogio = new THREE.Clock();
renderer.setAnimationLoop(()=>{
  const t = relogio.getElapsedTime(), v = pensando ? 2.5 : 1;
  globo.rotation.y = t*.3*v;
  robo.position.y = POS.robo[1] + Math.sin(t*1.5)*.08;
  robo.rotation.y = Math.sin(t*.6)*.35;
  olhoMat.color.setHex(pensando && Math.floor(t*6)%2 ? 0xffffff : 0x00e5ff);
  esfera.rotation.y = t*.5*v; anel.rotation.z = t*.8*v;
  zeus.update(t, pensando);
  renderer.render(scene, camera);
});

const msgs = document.getElementById("msgs"), txt = document.getElementById("txt");
function addMsg(classe, texto){
  const d = document.createElement("div"); d.className = "m " + classe; d.innerHTML = texto;
  msgs.appendChild(d); msgs.scrollTop = msgs.scrollHeight; return d;
}

async function enviar(){
  const mensagem = txt.value.trim(); if(!mensagem || pensando) return;
  txt.value = ""; addMsg("eu", "<b>Você:</b> " + mensagem);
  const espera = addMsg("ia", "<b>Zeus:</b> Pensando...");
  pensando = true;
  try{
    // Comunicação nativa otimizada com backend Streamlit Python
    const resposta = await window.streamlitBridge(mensagem);
    espera.innerHTML = "<b>Zeus:</b> " + resposta;
  }catch(e){
    espera.innerHTML = "<b>Zeus:</b> Erro de comunicação com o núcleo.";
  }
  pensando = false; msgs.scrollTop = msgs.scrollHeight;
}
document.getElementById("env").onclick = enviar;
txt.addEventListener("keydown", e => { if(e.key === "Enter") enviar(); });
</script></body></html>
"""

# Layout principal no Streamlit ocupando a tela inteira sem restrições
components.html(HTML_CODE, height=850, scrolling=False)
