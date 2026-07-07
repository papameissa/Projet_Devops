# Projet DevOps — ISI Dakar

**Sujet :** Mise en place d'une solution DevOps de conteneurisation et automatisation

**Étudiant :** Manny — Licence 3 Réseaux & Sécurité Informatique
**Établissement :** Institut Supérieur d'Informatique (ISI) — Dakar

## Application : task-app

Gestionnaire de tâches (manifeste opérationnel) — Flask + SQLAlchemy + PostgreSQL,
avec interface web et API JSON.

## Stack technique

- **Backend :** Python Flask + Flask-SQLAlchemy + PostgreSQL
- **Frontend :** Templates Jinja2 + CSS (pas de framework JS)
- **Conteneurisation :** Docker (multi-stage, non-root, healthcheck)
- **Registre :** Amazon ECR (repo `task-app`)
- **Orchestration :** Kubernetes sur AWS EKS (`devops-cluster`, 2× t3.micro)
- **IaC :** Ansible
- **CI/CD :** GitHub Actions (runners GitHub-hosted, ubuntu-latest)
- **Exposition :** AWS Network Load Balancer (Service `type: LoadBalancer`, annotation `aws-load-balancer-type: nlb`)
- **Autoscaling :** HPA (1-3 replicas) — nécessite `metrics-server` (installé automatiquement par le playbook 06)

## Structure du projet

```
/
├── app/                              ← Application Flask (task-app)
│   ├── app.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── templates/                    ← Interface web (Jinja2)
│   └── static/css/style.css
├── docker-compose.yml                ← Lancement local (app + Postgres)
├── .env                              ← Variables locales (non commité)
├── ansible/
│   ├── inventory/hosts.ini
│   ├── group_vars/all.yml            ← Source unique de toutes les variables (région, VPC, EKS, ECR, K8s, secrets)
│   ├── vault/                        ← Secrets chiffrés (ansible-vault), si utilisé
│   └── playbooks/
│       ├── 00_iam.yml                ← Utilisateur IAM CI/CD à moindre privilège (une fois)
│       ├── 01_vpc.yml                ← VPC devops-vpc (idempotent, sans NAT Gateway)
│       ├── 02_eks.yml                ← Cluster EKS DANS devops-vpc (recréable à la demande, ~15-20 min)
│       ├── 03_ecr.yml                ← [LEGACY] ancien repo "flask-app", inutilisé
│       ├── 04_ecr_taskapp.yml        ← Crée le repo ECR "task-app"
│       ├── deploy_complet.yml        ← Orchestrateur : 01→02→04→05→06 en une commande
│       ├── 07_destroy.yml            ← Détruit le cluster (+ VPC/ECR en option via tags)
│       ├── 05_build_push_taskapp.yml ← Build + push l'image vers ECR
│       └── 06_deploy_taskapp.yml     ← Déploie sur EKS (kubectl apply)
├── k8s/                              ← Manifests Kubernetes
│   ├── configmap.yaml
│   ├── secret.yaml                   ← Non commité (voir secret.yaml.example)
│   ├── secret.yaml.example
│   ├── postgres-deployment.yaml      ← StatefulSet Postgres
│   ├── postgres-service.yaml
│   ├── deployment.yaml               ← Deployment task-app
│   ├── service.yaml                  ← LoadBalancer (NLB)
│   └── hpa.yaml                      ← Autoscaling (1-3 replicas, t3.micro)
└── .github/workflows/ci-cd.yaml      ← Pipeline CI/CD
```

## Lancer en local (test)

```bash
docker-compose up --build
# Ouvre http://localhost:5000
```

## Sécurité mise en place

| Mesure | Où |
|---|---|
| Utilisateur non-root dans le conteneur | `app/Dockerfile` (UID 1000) |
| `securityContext` Kubernetes (non-root, capabilities dropped) | `k8s/deployment.yaml`, `k8s/postgres-deployment.yaml` |
| `NetworkPolicy` : seul task-app peut atteindre task-db:5432 | `k8s/networkpolicy.yaml` |
| Secret généré dynamiquement, jamais committé | `06_deploy_taskapp.yml` |
| Mot de passe chiffré (usage local) | `ansible/vault/` |
| Utilisateur IAM à moindre privilège (pas `AdministratorAccess`) | `00_iam.yml` |
| Tag ECR immuable + scan de vulnérabilités | `04_ecr_taskapp.yml` |
| Aucun SSH exposé (nodes sans clé, Ansible en `hosts: local`) | — |

**Point d'attention technique** : par défaut, EKS n'applique pas réellement les
`NetworkPolicy` (l'objet existe dans l'API sans effet). `02_eks.yml` active
`enableNetworkPolicy` sur l'addon `vpc-cni` pour que la policy soit vraiment
appliquée — vérifie `kubectl describe networkpolicy -n application` après
déploiement pour confirmer.

**Non couvert (périmètre volontairement limité pour un projet de licence)** :
HTTPS/TLS sur le NLB (trafic en clair), monitoring/observabilité (Prometheus,
CloudWatch Container Insights), sauvegarde automatisée du volume PostgreSQL —
à mentionner en perspectives d'amélioration dans le mémoire.

## Provisioning IAM (une seule fois, remplace AdministratorAccess)

```bash
ansible-playbook playbooks/00_iam.yml
# puis, manuellement (action sensible, jamais automatisée) :
aws iam create-access-key --user-name task-app-cicd
```

Crée un utilisateur IAM dédié avec une policy scoped par service et par préfixe
de ressource (`eksctl-devops-cluster-*`, repo ECR `task-app` uniquement) — à la
place d'un utilisateur `AdministratorAccess` qui donnerait un accès total au
compte. Copie les clés générées dans les GitHub Secrets, puis supprime toute
ancienne clé `AdministratorAccess` si tu en utilisais une.

## Tout enchaîner en une seule commande (orchestrateur)

```bash
cd ansible
ansible-playbook playbooks/deploy_complet.yml \
  -e "image_tag=v1" -e "postgres_user=app_user" \
  -e "@vault/secrets.yml" --ask-vault-pass
```

Équivalent à lancer `01_vpc.yml → 02_eks.yml → 04_ecr_taskapp.yml →
05_build_push_taskapp.yml → 06_deploy_taskapp.yml` dans l'ordre, jusqu'à
l'exposition de l'application via le NLB. Compter ~20-25 minutes (le cluster
EKS domine la durée). Chaque playbook reste utilisable séparément pour du
débogage ciblé.

## Détruire l'infrastructure (symétrique au provisioning)

```bash
ansible-playbook playbooks/07_destroy.yml                # cluster EKS uniquement (le coût principal)
ansible-playbook playbooks/07_destroy.yml --tags vpc      # + VPC complet
ansible-playbook playbooks/07_destroy.yml --tags ecr      # + repo ECR (supprime aussi les images)
ansible-playbook playbooks/07_destroy.yml --tags vpc,ecr  # tout détruire
```

Par défaut, seul le cluster est détruit (VPC et ECR sont conservés pour
repartir rapidement). Utilise `--tags vpc,ecr` uniquement en fin de projet,
une fois la soutenance passée.

## Déployer sur AWS

```bash
cd ansible/playbooks

# Si le VPC/cluster n'existent pas encore (ou ont été supprimés pour limiter les coûts) :
ansible-playbook 01_vpc.yml   # idempotent, ~1 min
ansible-playbook 02_eks.yml   # crée le cluster DANS devops-vpc, ~15-20 min, sans NAT Gateway

ansible-playbook 04_ecr_taskapp.yml        # une seule fois (idempotent si déjà créé)

ansible-playbook 05_build_push_taskapp.yml \
  -e "image_tag=v1"                        # à chaque nouvelle version

ansible-playbook 06_deploy_taskapp.yml \
  -e "image_tag=v1" \
  -e "postgres_user=app_user" \
  -e "postgres_password=CHANGE_MOI"        # applique les manifests K8s
```

Le namespace Kubernetes utilisé est `application` (créé automatiquement par le
playbook 06 s'il n'existe pas). Le Secret `task-secrets` n'est jamais lu depuis
un fichier commité : il est généré à la volée par Ansible à partir des
variables `postgres_user` / `postgres_password`.

## Gestion des coûts (important)

Le control plane EKS facture **0,10 $/heure en continu**, qu'il soit utilisé
ou non (~73$/mois si laissé actif 24h/24) — aucune exception, pas de Free Tier.
Entre deux sessions de travail prolongées (plusieurs jours), supprimer le
cluster et le recréer à la demande :

```bash
eksctl delete cluster --name devops-cluster --region us-east-1
# ... puis, pour repartir :
ansible-playbook playbooks/02_eks.yml
```

`devops-vpc`, le repo ECR `task-app` et les images poussées ne sont pas
affectés par cette suppression — seul le cluster (control plane + nodes) est
recréé, en quelques commandes grâce à l'automatisation Ansible.

## CI/CD

Le pipeline (`.github/workflows/ci-cd.yaml`) se déclenche sur chaque push vers `main` :

1. **lint** — flake8
2. **build-check** — vérifie que l'image Docker se build
3. **ansible-build-push** — exécute `05_build_push_taskapp.yml` (build + push ECR piloté par Ansible)
4. **ansible-deploy** — exécute `06_deploy_taskapp.yml` (namespace, secret, metrics-server, manifests K8s, piloté par Ansible)

Toute la logique d'exécution (provisioning, configuration, déploiement) passe
par Ansible ; GitHub Actions ne fait qu'orchestrer les étapes et fournir les
identifiants. Le pipeline tourne sur des runners GitHub-hosted (`ubuntu-latest`), sans EC2 dédiée à gérer.

### Secrets GitHub requis (Settings → Secrets and variables → Actions)

| Secret | Description |
|---|---|
| `AWS_ACCESS_KEY_ID` | Clé IAM avec droits ECR + EKS |
| `AWS_SECRET_ACCESS_KEY` | Secret associé |
| `POSTGRES_USER` | Utilisateur de la base PostgreSQL |
| `POSTGRES_PASSWORD` | Mot de passe de la base PostgreSQL |

`AWS_REGION` est fixée en dur à `us-east-1` dans le workflow (variable `env`),
plus besoin de la dupliquer en secret. `ECR_REPOSITORY` n'est plus nécessaire :
l'URI ECR est reconstruite dynamiquement par Ansible à partir du compte AWS
courant (`aws sts get-caller-identity`).
