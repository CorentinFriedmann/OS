// Nova OS — halo néon discret autour du texte (shader Ghostty, style Shadertoy).
// Statique (custom-shader-animation = false) : rien n'est recalculé tant que
// l'écran ne change pas, donc quasiment aucun impact sur la batterie.

const float RADIUS = 2.2;    // rayon du halo, en pixels
const float STRENGTH = 0.30; // intensité du halo
const int TAPS = 12;

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 uv = fragCoord / iResolution.xy;
    vec4 base = texture(iChannel0, uv);
    vec2 px = RADIUS / iResolution.xy;

    vec3 glow = vec3(0.0);
    for (int i = 0; i < TAPS; i++) {
        float angle = 6.2831853 * float(i) / float(TAPS);
        vec3 c = texture(iChannel0, uv + vec2(cos(angle), sin(angle)) * px).rgb;
        // Seules les zones lumineuses (le texte) rayonnent, pas le fond sombre
        float luminance = dot(c, vec3(0.2126, 0.7152, 0.0722));
        glow += c * smoothstep(0.35, 0.9, luminance);
    }
    glow /= float(TAPS);

    fragColor = vec4(base.rgb + glow * STRENGTH, base.a);
}
