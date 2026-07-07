# Ansible Vault — mot de passe PostgreSQL en local

Ce dossier chiffre `postgres_password` pour les exécutions **manuelles** en
local (déploiement depuis Kali/Windows). En CI/CD, ce vault n'est **pas**
utilisé : le pipeline injecte `postgres_user`/`postgres_password` directement
depuis les GitHub Secrets (`-e postgres_password=${{ secrets.POSTGRES_PASSWORD }}`).

`secrets.yml` (le vrai fichier, chiffré) est volontairement listé dans
`.gitignore` : même chiffré, on ne le committe pas, pour rester cohérent avec
le reste du projet (aucun secret, même protégé, ne transite par le dépôt).

## 1. Créer le vault (une seule fois)

```bash
cd ansible
ansible-vault create vault/secrets.yml
```

Ansible demande un mot de passe de chiffrement (choisis-en un, à retenir —
c'est la clé qui protège le fichier). Un éditeur s'ouvre : colle exactement

```yaml
postgres_password: "TON_VRAI_MOT_DE_PASSE"
```

Sauvegarde et quitte. Le fichier `vault/secrets.yml` est maintenant chiffré
sur disque (illisible en clair, même en l'ouvrant avec `cat`).

## 2. Utiliser le vault lors d'un déploiement manuel

```bash
cd ansible
ansible-playbook playbooks/06_deploy_taskapp.yml \
  -e "image_tag=v1" \
  -e "postgres_user=app_user" \
  -e "@vault/secrets.yml" \
  --ask-vault-pass
```

`--ask-vault-pass` demande le mot de passe de chiffrement au moment de
l'exécution ; `-e "@vault/secrets.yml"` charge `postgres_password` depuis le
fichier déchiffré à la volée (jamais écrit en clair sur disque).

## 3. Consulter ou modifier le vault plus tard

```bash
ansible-vault view vault/secrets.yml      # lire sans modifier
ansible-vault edit vault/secrets.yml      # modifier (redemande le mot de passe)
```

## 4. Éviter de retaper le mot de passe à chaque fois (optionnel, local uniquement)

```bash
echo "TON_MOT_DE_PASSE_VAULT" > ~/.vault_pass.txt
chmod 600 ~/.vault_pass.txt
```

Puis remplace `--ask-vault-pass` par `--vault-password-file ~/.vault_pass.txt`.
**Ne mets jamais ce fichier dans le projet ni dans git** — il doit rester en
dehors du dépôt (ex. dans ton `$HOME`).
