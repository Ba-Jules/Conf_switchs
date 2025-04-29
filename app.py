import os
import requests
import pandas as pd
from flask import Flask, request, render_template, session, redirect, url_for, flash, send_file
from dotenv import load_dotenv
import uuid
import time

# Charger les variables d'environnement
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "une_clé_secrète_par_défaut")

# Récupérer les clés API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Créer un dossier pour stocker les fichiers temporaires s'il n'existe pas
TEMP_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
if not os.path.exists(TEMP_FOLDER):
    os.makedirs(TEMP_FOLDER)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        ai_provider = request.form.get('ai_provider', 'anthropic')
        
        # Traitement du fichier ou du texte DEX
        if 'dex_file' in request.files and request.files['dex_file'].filename != '':
            dex_file = request.files['dex_file']
            
            # Vérifier l'extension du fichier
            if not dex_file.filename.endswith(('.xlsx', '.xls', '.csv')):
                flash("Seuls les fichiers Excel (.xlsx, .xls) ou CSV sont acceptés")
                return redirect(url_for('index'))
            
            try:
                # Lire le fichier Excel/CSV
                if dex_file.filename.endswith('.csv'):
                    df = pd.read_csv(dex_file)
                else:
                    df = pd.read_excel(dex_file)
                
                # Convertir le DEX en format texte
                dex_content = convert_excel_to_text(df)
            except Exception as e:
                flash(f"Erreur lors de la lecture du fichier: {str(e)}")
                return redirect(url_for('index'))
        else:
            # Utiliser le texte DEX du formulaire
            dex_content = request.form.get('dex_content', '')
            
        if not dex_content:
            flash("Veuillez fournir un DEX, soit en texte soit en fichier Excel.")
            return redirect(url_for('index'))
        
        # Générer un identifiant unique pour cette session
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
        
        # Enregistrer le contenu DEX dans un fichier temporaire
        dex_file_path = os.path.join(TEMP_FOLDER, f"dex_{session_id}.txt")
        with open(dex_file_path, 'w', encoding='utf-8') as f:
            f.write(dex_content)
        
        # Traiter le DEX en phases
        try:
            config = process_dex_in_phases(dex_content, ai_provider)
        except Exception as e:
            config = f"Erreur lors de la génération: {str(e)}"
        
        # Enregistrer la configuration générée
        config_file_path = os.path.join(TEMP_FOLDER, f"config_{session_id}.txt")
        with open(config_file_path, 'w', encoding='utf-8') as f:
            f.write(config)
        
        return redirect(url_for('result'))
    
    return render_template('index.html')

@app.route('/result')
def result():
    session_id = session.get('session_id')
    if not session_id:
        flash("Session expirée ou invalide")
        return redirect(url_for('index'))
    
    # Lire la configuration générée depuis le fichier temporaire
    config_file_path = os.path.join(TEMP_FOLDER, f"config_{session_id}.txt")
    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            generated_config = f.read()
    except:
        generated_config = 'Aucune configuration générée'
    
    return render_template('result.html', config=generated_config)

@app.route('/download')
def download():
    session_id = session.get('session_id')
    if not session_id:
        flash("Session expirée ou invalide")
        return redirect(url_for('index'))
    
    config_file_path = os.path.join(TEMP_FOLDER, f"config_{session_id}.txt")
    return send_file(config_file_path, as_attachment=True, download_name="switch_configuration.txt")

def convert_excel_to_text(df):
    """Convertir un DataFrame en format texte utilisable pour le DEX"""
    import io
    buffer = io.StringIO()
    
    # Affichage des colonnes
    buffer.write("\t".join(str(col) for col in df.columns))
    buffer.write("\n")
    
    # Affichage des données
    for _, row in df.iterrows():
        buffer.write("\t".join(str(val) for val in row))
        buffer.write("\n")
    
    return buffer.getvalue()

def process_dex_in_phases(dex_content, ai_provider):
    """Traite le DEX en plusieurs phases pour rester dans les limites de tokens"""
    
    print(f"Phase 1: Génération de la configuration système de base...")
    # Phase 1: Configuration système de base
    phase1_prompt = build_system_prompt(dex_content)
    if ai_provider == 'anthropic':
        phase1_config = generate_config_claude(phase1_prompt)
    else:
        phase1_config = generate_config_openai(phase1_prompt)
    
    print(f"Phase 2: Génération des interfaces d'agrégation...")
    # Phase 2: Configuration des interfaces d'agrégation
    phase2_prompt = build_aggregation_prompt(dex_content, phase1_config)
    if ai_provider == 'anthropic':
        phase2_config = generate_config_claude(phase2_prompt)
    else:
        phase2_config = generate_config_openai(phase2_prompt)
    
    print(f"Phase 3: Génération des interfaces physiques...")
    # Phase 3: Configuration des interfaces physiques
    phase3_prompt = build_physical_prompt(dex_content, phase1_config, phase2_config)
    if ai_provider == 'anthropic':
        phase3_config = generate_config_claude(phase3_prompt)
    else:
        phase3_config = generate_config_openai(phase3_prompt)
    
    # Combiner les configurations
    full_config = phase1_config + "\n\n" + phase2_config + "\n\n" + phase3_config
    
    return full_config

def build_system_prompt(dex_content):
    """Construire le prompt pour la configuration système"""
    prompt = """Agis comme un expert réseau spécialisé dans la configuration des switches H3C/HPE des séries A5500HI/5900. Génère la PREMIÈRE PARTIE de la configuration CLI Comware à partir du Document d'Exploitation (DEX) fourni.

Pour cette première partie, concentre-toi UNIQUEMENT sur:

1. CONFIGURATION SYSTÈME ET IRF
   - Définis le hostname selon le format indiqué dans le DEX (généralement le nom du premier équipement du stack avec suffixe "-s")
   - Pour la configuration IRF, utilise la commande easy-irf:
     * Pour le membre 1: "easy-irf member 1 renumber 1 domain [DOMAIN] priority [PRIORITÉ] irf-port1 [PORT1] irf-port2 [PORT2]"
     * Pour le membre 2: "easy-irf member 1 renumber 2 domain [DOMAIN] priority [PRIORITÉ] irf-port1 [PORT1] irf-port2 [PORT2]"
   - Le domain IRF est calculé à partir des 3 derniers octets de l'adresse IP (ex: 172.19.97.51 => domain 019097051)
   - Les ports IRF sont généralement ceux indiqués dans le DEX (souvent FortyGigE ou HundredGigE)

2. CONFIGURATION DES VLANS
   - Crée tous les VLANs listés dans le DEX avec leur description exacte et name
   - Ajoute toujours le VLAN 4093 (description "Vlan MAD-BFD", name "Vlan MAD-BFD")
   - Ajoute toujours le VLAN 4094 (description "Vlan Poubelle", name "Vlan Poubelle")
   - Pour chaque VLAN, utilise la syntaxe:
     ```
     vlan [NUMERO]
      description [DESCRIPTION]
      name [DESCRIPTION]
     ```

3. INTERFACES VLAN ET ROUTAGE
   - Configure les interfaces SVI (VLAN interfaces) avec leurs adresses IP
   - Configure la route statique par défaut avec la syntaxe:
     ```
     ip route-static 0.0.0.0 0.0.0.0 [GATEWAY] preference 60
     ```

4. SERVICES RÉSEAU ET SÉCURITÉ
   - Configure NTP avec les serveurs indiqués dans le DEX:
     ```
     ntp-service enable
     ntp-service unicast-server [SERVER_IP] version 4
     clock timezone CEST add 1
     clock summer-time ETE 02:00:00 March last Sunday 03:00:00 October last Sunday 01:00:00
     ```
   - Configure Syslog:
     ```
     info-center loghost [SYSLOG_IP] facility local7
     info-center timestamp loghost no-year-date
     ```
   - Configure SNMP:
     ```
     snmp-agent
     undo snmp-agent sys-info version v3
     snmp-agent sys-info version v1 v2c
     snmp-agent community read rsprv
     snmp-agent group v1 rsprv
     snmp-agent group v2c rsprv
     ```
   - Désactive les services non sécurisés:
     ```
     undo ip http enable
     undo ip https enable
     undo telnet server enable
     lldp global enable
     undo gvrp
     undo ndp enable
     ```

5. COMPTES UTILISATEURS ET INTERFACES D'ACCÈS
   - Configure les comptes administrateur et utilisateur:
     ```
     local-user admsnant class manage
     password simple admsnant
     service-type ssh terminal
     authorization-attribute user-role network-admin
     
     local-user usrsnant class manage
     password simple usrsnant
     service-type ssh terminal
     authorization-attribute user-role network-operator
     ```
   - Configure SSH:
     ```
     ssh server enable
     ssh server compatible-ssh1x enable
     public-key local create rsa
     ssh user admsnant service-type stelnet authentication-type password
     ssh user usrsnant service-type stelnet authentication-type password
     ```
   - Configure les interfaces utilisateur:
     ```
     user-interface aux 0 1
     authentication-mode scheme
     user-role network-admin
     
     user-interface vty 0 15
     authentication-mode scheme
     user-role network-admin
     protocol inbound ssh
     ```

6. CONFIGURATION MAD-BFD
   - Configure l'interface MAD-BFD:
     ```
     interface vlan-interface4093
     mad bfd enable
     mad ip address 192.168.1.1 255.255.255.0 member 1
     mad ip address 192.168.1.2 255.255.255.0 member 2
     ```

7. SPANNING TREE ET AUTRES PROTOCOLES
   - Configure STP:
     ```
     stp global enable
     stp bpdu-protection
     stp pathcost-standard dot1t
     ```

N'INCLUS PAS les sections suivantes (elles seront générées dans les parties suivantes):
- N'inclus PAS les interfaces d'agrégation (Bridge-Aggregation)
- N'inclus PAS les interfaces physiques (Ten-GigabitEthernet, etc.)

Voici le DEX complet:
{dex_content}

Génère uniquement le code de configuration CLI Comware pour cette première partie, sans explications supplémentaires. Utilise des commentaires (#) pour séparer clairement les sections."""
    
    return prompt.format(dex_content=dex_content)

def build_aggregation_prompt(dex_content, phase1_config):
    """Construire le prompt pour la configuration des interfaces d'agrégation"""
    prompt = """Agis comme un expert réseau spécialisé dans la configuration des switches H3C/HPE des séries A5500HI/5900. Génère la DEUXIÈME PARTIE de la configuration CLI Comware à partir du Document d'Exploitation (DEX) fourni.

Voici la première partie de la configuration déjà générée que tu dois prendre en compte:
{phase1_config}

Pour cette deuxième partie, concentre-toi UNIQUEMENT sur la CONFIGURATION DES INTERFACES D'AGRÉGATION:

1. Crée toutes les interfaces Bridge-Aggregation mentionnées dans le DEX
2. Configure chaque agrégation avec:
   - Description appropriée (extrait du DEX)
   - Mode d'agrégation (dynamic pour LACP, static sinon)
     ```
     link-aggregation mode dynamic
     ```
   - Configuration VLAN (trunk, VLANs autorisés, PVID)
     ```
     port link-type trunk
     undo port trunk permit vlan 1
     port trunk permit vlan [VLANS]
     port trunk pvid vlan [PVID]
     ```
   - Configuration STP (enable/disable/edge)
     ```
     stp edged-port
     ```
     ou
     ```
     undo stp enable
     ```

Assure-toi que les VLANs mentionnés correspondent à ceux définis dans la première partie.
Utilise le format suivant pour chaque interface d'agrégation:

```
interface Bridge-Aggregation[NUMERO]
 description [DESCRIPTION]
 port link-type trunk
 undo port trunk permit vlan 1
 port trunk permit vlan [VLANS]
 port trunk pvid vlan [PVID]
 link-aggregation mode dynamic
 [STP_CONFIG]
```

N'INCLUS PAS les interfaces physiques (Ten-GigabitEthernet, etc.) - elles seront générées dans la partie suivante.

Voici le DEX complet:
{dex_content}

Génère uniquement le code de configuration CLI Comware pour les interfaces d'agrégation, sans explications supplémentaires. Utilise un commentaire (#) au début pour marquer cette section."""
    
    return prompt.format(dex_content=dex_content, phase1_config=phase1_config)
def build_physical_prompt(dex_content, phase1_config, phase2_config):
    """Construire le prompt pour la configuration des interfaces physiques"""
    prompt = """Agis comme un expert réseau spécialisé dans la configuration des switches H3C/HPE des séries A5500HI/5900. Génère la TROISIÈME PARTIE de la configuration CLI Comware à partir du Document d'Exploitation (DEX) fourni.

Voici la première partie de la configuration déjà générée que tu dois prendre en compte:
{phase1_config}

Voici la configuration des interfaces d'agrégation déjà générée:
{phase2_config}

Pour cette troisième partie, concentre-toi UNIQUEMENT sur la CONFIGURATION DES INTERFACES PHYSIQUES:

IMPORTANT: Tu dois générer la configuration COMPLÈTE et DÉTAILLÉE pour CHAQUE port physique mentionné dans le DEX. N'utilise PAS de commentaires comme "... (configuration similaire)" ou "... (etc.)". Fournis la configuration exacte et complète pour tous les ports, même si cela semble répétitif.

1. Configure chaque port physique selon son type dans le DEX:

   A. Pour les ports MAD (généralement XGE1/0/1 et XGE2/0/1):
      ```
      interface Ten-GigabitEthernet1/0/1
       description [ÉQUIPEMENT_CONNECTÉ]-[PORT] (MAD)
       port access vlan 4093
       undo shutdown
       undo stp enable
      ```

   B. Pour les ports membre d'une agrégation (avec BAGG dans le DEX):
      ```
      interface Ten-GigabitEthernet[X/Y/Z]
       description [ÉQUIPEMENT_CONNECTÉ]-[PORT]
       port link-aggregation group [NUMERO]
       speed [VITESSE]
       undo shutdown
       stp edged-port
      ```
      * Ne configure PAS les VLANs sur ces ports - ils héritent de la configuration de l'agrégation
      * Inclus uniquement: description, link-aggregation, speed, shutdown, stp

   C. Pour les ports en mode access (sans BAGG):
      ```
      interface Ten-GigabitEthernet[X/Y/Z]
       description [ÉQUIPEMENT_CONNECTÉ]-[PORT]
       port access vlan [VLAN]
       speed [VITESSE]
       undo shutdown
       stp edged-port
      ```

   D. Pour les ports en mode trunk non agrégés:
      ```
      interface Ten-GigabitEthernet[X/Y/Z]
       description [ÉQUIPEMENT_CONNECTÉ]-[PORT]
       port link-type trunk
       undo port trunk permit vlan 1
       port trunk permit vlan [VLANS]
       port trunk pvid vlan [PVID]
       speed [VITESSE]
       undo shutdown
       stp edged-port
      ```

   E. Pour les groupes de ports non utilisés:
      ```
      interface range Ten-GigabitEthernet[X/Y/Z] to Ten-GigabitEthernet[X/Y/W]
       shutdown
      ```
      ou
      ```
      interface Ten-GigabitEthernet[X/Y/Z]
       shutdown
      ```

2. La description doit inclure l'équipement connecté et son port:
   - Format: "description [ÉQUIPEMENT]-[PORT]"
   - Note: les switches ont généralement un nom qui finit par "clXXX" (ex: Biapulc006)

3. Pour les ports membres de la même agrégation:
   - Applique la même configuration de speed, shutdown, et stp
   - Assure-toi que tous les ports sont bien assignés au même groupe

RAPPEL: Ne pas utiliser de raccourcis ou de commentaires du type "... (configuration similaire)" - l'objectif est de fournir une configuration complète et prête à l'emploi qui puisse être copiée-collée directement.

Termine par la commande "save" à la fin de la configuration.

Voici le DEX complet:
{dex_content}

Génère uniquement le code de configuration CLI Comware pour les interfaces physiques, sans explications supplémentaires. Utilise un commentaire (#) au début pour marquer cette section."""
    
    return prompt.format(dex_content=dex_content, phase1_config=phase1_config, phase2_config=phase2_config)

def generate_config_claude(prompt):
    """Générer la configuration à l'aide de l'API Claude d'Anthropic"""
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01"  # En-tête requis par l'API
    }
    
    data = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 4000,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        print(f"Envoi de la requête à l'API Anthropic...")
        response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=data)
        
        print(f"Statut de la réponse: {response.status_code}")
        if response.status_code != 200:
            print(f"Erreur API: {response.text}")
            return f"Erreur API {response.status_code}: {response.text}"
            
        response_data = response.json()
        return response_data["content"][0]["text"]
    except Exception as e:
        print(f"Exception lors de l'appel API: {str(e)}")
        return f"Erreur lors de la génération de la configuration avec Claude: {str(e)}"

def generate_config_openai(prompt):
    """Générer la configuration à l'aide de l'API OpenAI"""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 4000
    }
    
    try:
        print(f"Envoi de la requête à l'API OpenAI...")
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        
        print(f"Statut de la réponse: {response.status_code}")
        if response.status_code != 200:
            print(f"Erreur API: {response.text}")
            return f"Erreur API {response.status_code}: {response.text}"
            
        response_data = response.json()
        return response_data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Exception lors de l'appel API: {str(e)}")
        return f"Erreur lors de la génération de la configuration avec OpenAI: {str(e)}"

# Tâche de nettoyage des fichiers temporaires (plus de 24h)
def clean_temp_files():
    current_time = time.time()
    for filename in os.listdir(TEMP_FOLDER):
        file_path = os.path.join(TEMP_FOLDER, filename)
        if os.path.isfile(file_path):
            # Supprimer les fichiers de plus de 24 heures
            if current_time - os.path.getmtime(file_path) > 86400:
                os.remove(file_path)

if __name__ == '__main__':
    # Nettoyer les fichiers temporaires au démarrage
    clean_temp_files()
    app.run(debug=True)