# ╔══════════════════════════════════════════════════════════════╗
# ║  NOVA OS — shell fish (installé dans /etc/fish/conf.d)        ║
# ╚══════════════════════════════════════════════════════════════╝
# Tes réglages vont dans ~/.config/fish/config.fish (chargé après celui-ci).

status is-interactive; or return

set -g fish_greeting

# Couleurs « verre » (appliquées une seule fois : fish_config reste libre ensuite)
if not set -q nova_colors_v1
    set -U fish_color_command 8ab4ff
    set -U fish_color_keyword b9adff
    set -U fish_color_param eef1f6
    set -U fish_color_quote f2cf86
    set -U fish_color_redirection a4adbd
    set -U fish_color_operator b9adff
    set -U fish_color_end a4adbd
    set -U fish_color_error ff8f8f
    set -U fish_color_comment 4b5263
    set -U fish_color_autosuggestion 4b5263
    set -U fish_color_valid_path --underline
    set -U fish_pager_color_prefix 8ab4ff --bold
    set -U fish_pager_color_completion d5dbe6
    set -U fish_pager_color_description a4adbd
    set -U fish_pager_color_selected_background --background=1a2040
    set -U nova_colors_v1 1
end

# Invite (starship)
if type -q starship
    if not set -q STARSHIP_CONFIG
        if test -f ~/.config/starship.toml
            set -gx STARSHIP_CONFIG ~/.config/starship.toml
        else
            set -gx STARSHIP_CONFIG /usr/share/nova/starship.toml
        end
    end
    starship init fish | source
end

type -q zoxide; and zoxide init fish | source

# Outils modernes, mêmes réflexes
if type -q eza
    alias ls 'eza --icons --group-directories-first'
    alias ll 'eza -l --icons --git --group-directories-first'
    alias la 'eza -la --icons --git --group-directories-first'
    alias tree 'eza --tree --icons'
end
type -q bat; and alias cat 'bat --paging=never --style=plain'
alias maj nova-update

# Carte d'identité Nova à l'ouverture d'un terminal
if type -q fastfetch; and not set -q NOVA_FETCH_SHOWN; and test "$TERM_PROGRAM" != vscode
    set -gx NOVA_FETCH_SHOWN 1
    set -l fetch_config (nova-config fastfetch/config.jsonc 2>/dev/null)
    if test "$TERM" = xterm-ghostty -o "$TERM" = xterm-kitty
        fastfetch --config $fetch_config --logo-type kitty-direct --logo /usr/share/pixmaps/nova-logo.png --logo-width 16 --logo-height 8
    else
        fastfetch --config $fetch_config
    end
end
