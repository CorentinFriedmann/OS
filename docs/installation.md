# Installer Nova OS à côté de Windows

Ce guide installe Nova OS **en plus de Windows**, sur le même disque : au démarrage du PC, un
menu te laisse choisir entre les deux. Windows n'est ni modifié, ni redimensionné : c'est toi
qui libères de la place depuis Windows, et Nova s'installe uniquement dans cet espace libre.

**Durée** : environ 45 minutes, dont 15 à 30 de téléchargement pendant l'installation.

**Il te faut** :

- un PC avec Windows 10 ou 11 (démarrage UEFI, c'est le cas de tous les PC récents) ;
- une clé USB d'au moins 4 Go (8 Go conseillés) : **elle sera effacée** ;
- au moins **30 Go** libres sur le disque (**60 Go conseillés**, plus si tu joues beaucoup) ;
- une connexion à internet (Wi-Fi ou câble).

---

## 1. Sauvegarde

L'installateur ne touche jamais aux partitions de Windows, et il garde une copie de la table
des partitions. Mais une sauvegarde de tes fichiers importants (disque externe, OneDrive…)
reste la meilleure assurance avant toute installation.

## 2. Préparer Windows

### 2.1 Noter la clé de récupération BitLocker

Beaucoup de PC portables sous Windows 11 chiffrent le disque (BitLocker ou « chiffrement de
l'appareil »). Changer un réglage du BIOS peut alors déclencher une demande de **clé de
récupération** au démarrage suivant de Windows.

1. Vérifie : *Paramètres → Confidentialité et sécurité → Chiffrement de l'appareil* (ou
   *Panneau de configuration → Chiffrement de lecteur BitLocker*).
2. Si c'est activé, récupère ta clé sur [aka.ms/myrecoverykey](https://aka.ms/myrecoverykey)
   (compte Microsoft) et note-la **hors du PC** (papier, photo avec ton téléphone).
3. Conseillé : *Chiffrement de lecteur BitLocker → **Interrompre la protection*** juste
   avant de modifier le BIOS (étape 4). Elle se réactive toute seule au redémarrage suivant
   de Windows.

### 2.2 Désactiver le démarrage rapide

Le « démarrage rapide » de Windows ne s'éteint jamais vraiment, ce qui peut gêner le partage
du matériel avec Nova (Wi-Fi, horloge, disques).

*Panneau de configuration → Options d'alimentation → Choisir l'action des boutons
d'alimentation → Modifier des paramètres actuellement non disponibles →* décoche
**Activer le démarrage rapide** → *Enregistrer*.

### 2.3 Libérer de la place pour Nova

1. Clic droit sur le bouton Démarrer → **Gestion du disque**.
2. Clic droit sur **C:** → **Réduire le volume…**
3. Dans « Quantité d'espace à réduire (en Mo) », tape **61440** pour 60 Go
   (minimum 30720 pour 30 Go) → **Réduire**.
4. Un espace **« Non alloué »** apparaît. **Ne crée pas de partition dedans** : l'installateur
   de Nova s'en charge.

> Windows refuse de réduire autant que tu voudrais ? Désactive temporairement la mise en
> veille prolongée (invite de commandes en administrateur : `powercfg /h off`), redémarre,
> puis réessaie. Tu pourras la réactiver ensuite avec `powercfg /h on`.

## 3. Créer la clé USB de Nova

1. Télécharge la dernière version sur la page
   [Releases](https://github.com/CorentinFriedmann/OS/releases/latest) :
   le fichier **`novaos-….iso`** et **`SHA256SUMS`**.
   *(Si l'image est en plusieurs morceaux `.part0`, `.part1`…, la page de la version explique
   comment les recoller en une commande.)*
2. Facultatif, vérifier le téléchargement : dans PowerShell,
   `Get-FileHash .\novaos-*.iso -Algorithm SHA256`, puis compare avec `SHA256SUMS`.
3. Écris l'image sur la clé, avec l'un de ces outils :
   - **[Rufus](https://rufus.ie)** (conseillé) : choisis la clé, puis l'ISO, puis *Démarrer*.
     Quand Rufus le demande, choisis **« Écrire en mode Image DD »**.
   - **[Ventoy](https://www.ventoy.net)** : copie simplement l'ISO sur une clé Ventoy (pratique
     si tu y gardes d'autres systèmes).
   - **[balenaEtcher](https://etcher.balena.io)** : *Flash from file → Select target → Flash*.

## 4. Régler le BIOS / UEFI

Pour ouvrir les réglages du BIOS depuis Windows : *Paramètres → Système → Récupération →
Démarrage avancé → Redémarrer maintenant → Dépannage → Options avancées → **Paramètres du
microprogramme UEFI** → Redémarrer*. (Sinon, au démarrage, appuie sur **F2**, **Suppr**,
**F10** sur HP, ou **F1** sur ThinkPad.)

- **Secure Boot → Disabled** (désactivé). Nova n'est pas encore signé pour le démarrage sécurisé.
- Reste en mode **UEFI** (pas de « Legacy » ni de « CSM »).
- Enregistre et quitte (souvent **F10**).

## 5. Démarrer sur la clé

1. Branche la clé et redémarre le PC.
2. Ouvre le **menu de démarrage** en appuyant plusieurs fois, dès l'allumage, sur :
   **F12** (Dell, Lenovo, Acer), **F9** (HP), **Échap** ou **F8** (Asus), **F11** (MSI).
3. Choisis l'entrée **« UEFI : … »** qui porte le nom de ta clé.
4. Dans le menu de la clé, valide **« Nova OS — essai et installation »**.

Le bureau Nova démarre tout seul, sans mot de passe : c'est une **session d'essai**, rien
n'est modifié sur ton PC. Le clavier est en AZERTY.

## 6. Installer

1. Connecte-toi à internet : icône réseau en haut à droite (ou `nmtui` dans un terminal).
2. Dans la notification « Bienvenue dans Nova OS », clique sur **Installer**.
   *(Ou : Super+D → « Installer Nova OS », ou Super+Entrée puis `sudo nova-install`.)*
3. Réponds aux questions :

   | Étape | Choix |
   |---|---|
   | Disque | celui marqué **« Windows détecté »** |
   | Mode | **« À côté de Windows — dans l'espace libre »** |
   | Toi | prénom, nom d'utilisateur, mot de passe (sert aussi pour l'administration), nom du PC |
   | Langue et clavier | Français (AZERTY) par défaut, fuseau Europe/Paris |
   | Logiciels | Jeux, Développement, Quotidien et multimédia (tout est coché, Espace pour décocher) |

4. Vérifie le **récapitulatif**, puis confirme.
5. Patiente pendant le téléchargement et l'installation. À la fin : **« Nova OS est installé ! »**.
6. Retire la clé USB et redémarre.

### Ce que fait l'installateur, exactement

- Il **sauvegarde la table des partitions** avant toute écriture (une copie est gardée sur le
  système installé, dans `/var/lib/nova/`).
- Il crée **une seule nouvelle partition** « Nova OS » dans l'espace non alloué.
- Il réutilise la partition EFI de Windows **sans la formater** : il y ajoute seulement un
  dossier `EFI/Nova` (le chargeur de Windows n'est pas touché).
- Il refuse de continuer s'il n'y a pas assez de place, plutôt que de toucher à Windows.
- En mode « Effacer tout le disque » (PC sans Windows), il faut taper **EFFACER** pour confirmer.

Ce comportement est vérifié automatiquement à chaque version : une machine virtuelle installe
Nova à côté d'un faux Windows, puis vérifie que les partitions de Windows sont **identiques au
bit près** et que les deux systèmes apparaissent au menu de démarrage.

## 7. Premier démarrage

Le **menu néon** de Nova s'affiche quelques secondes :

| Entrée | Rôle |
|---|---|
| **Nova OS** | choisi automatiquement après 5 secondes |
| Options avancées pour Nova OS | noyau de secours (LTS), si une mise à jour du noyau pose problème |
| **Windows Boot Manager** | démarrer Windows |
| Instantanés Nova (retour en arrière) | apparaît après les premières mises à jour, voir plus bas |
| Paramètres du micrologiciel UEFI | ouvrir le BIOS |

Ensuite : connecte-toi, et Nova se présente.

- **Super+F1** : tous les raccourcis ([la liste](raccourcis.md)) ;
- **Super+Espace** : parler à Nova ([l'assistant](assistant.md)), clic droit sur l'orbe ✦ de
  la barre pour le régler ;
- pour retourner sous Windows : menu d'alimentation (**Super+Échap**) → **Redémarrer sous
  Windows** (une seule fois, Nova reste le choix par défaut).

## Mises à jour et retour en arrière

- **Mettre à jour** : demande à Nova « mets à jour le système », ou lance `nova-update` dans un
  terminal (paquets, logiciels Flatpak et micrologiciels en une fois).
- **Instantanés automatiques** : avant et après chaque installation ou mise à jour, Nova prend
  un instantané du système (snapper). Si une mise à jour casse quelque chose, choisis
  **« Instantanés Nova (retour en arrière) »** dans le menu de démarrage, puis l'instantané
  d'avant la mise à jour : tu retrouves un système qui marche.

<details>
<summary>Rendre le retour en arrière définitif (avancé)</summary>

Une fois démarré sur l'instantané qui marche :

```bash
sudo snapper list    # repère le numéro N de cet instantané
sudo mount -o subvolid=5 "$(findmnt -no SOURCE / | sed 's/\[.*//')" /mnt
sudo mv /mnt/@ /mnt/@.casse
sudo btrfs subvolume snapshot /mnt/@snapshots/N/snapshot /mnt/@
sudo umount /mnt
sudo reboot
```

Tes fichiers personnels (`/home`) ne sont pas concernés : ils ont leur propre sous-volume.
Quand tout va bien, l'ancien système peut être supprimé : `sudo btrfs subvolume delete /mnt/@.casse`
(après avoir remonté `/mnt` comme ci-dessus).
</details>

## Dépannage

**Le PC démarre directement sur Windows, sans menu.**
Le BIOS a remis Windows en premier. Dans le BIOS, rubrique *Boot* / *Ordre de démarrage*,
place **« Nova »** en premier.

**Windows n'apparaît pas dans le menu de démarrage.**
Nova vérifie ça tout seul au premier démarrage. Sinon, dans un terminal :
`sudo grub-mkconfig -o /boot/grub/grub.cfg`.

**Windows demande la clé de récupération BitLocker.**
Saisis la clé notée à l'étape 2.1 : Windows démarre normalement ensuite. Ça arrive une fois,
après le changement de réglage du BIOS.

**L'installateur ne trouve aucun disque.**
Sur certains PC Intel, le disque est en mode « RAID / Intel RST / VMD ». Dans le BIOS, passe
le contrôleur de stockage en **AHCI** (ou désactive *VMD*). ⚠ Windows doit y être préparé, sinon
il ne démarre plus : avant de changer le réglage, invite de commandes en administrateur →
`bcdedit /set {current} safeboot minimal`, redémarre dans le BIOS, passe en AHCI, laisse
Windows démarrer (en mode sans échec), puis `bcdedit /deletevalue {current} safeboot` et redémarre.

**Pas de Wi-Fi dans la session d'essai.**
Branche un câble réseau, ou partage la connexion de ton téléphone en USB.

**L'heure de Windows est décalée après être passé par Nova.**
Nova règle l'horloge en heure locale, comme Windows, donc ça ne devrait pas arriver. Sinon :
`sudo timedatectl set-local-rtc 1`.

**Un souci pendant l'installation ?**
Le journal détaillé est dans `/var/log/nova-install.log` (sur la clé, puis copié sur le système
installé).

## Désinstaller Nova

Depuis Windows :

1. *Gestion du disque* → clic droit sur la partition de Nova (sans lettre, de la taille que tu
   lui avais donnée) → **Supprimer le volume**, puis clic droit sur C: → **Étendre le volume**.
2. Retirer l'entrée du menu de démarrage, dans une invite de commandes **en administrateur** :

   ```bat
   mountvol S: /S
   rmdir /S /Q S:\EFI\Nova
   mountvol S: /D
   ```

   puis, dans le BIOS, remets **Windows Boot Manager** en premier si besoin.
