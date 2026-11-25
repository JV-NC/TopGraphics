# Créditos e licenças de áudio — TOP GRAPHICS

Este documento registra as fontes dos efeitos sonoros, ambientes e trilhas musicais efetivamente utilizados no **TOP GRAPHICS — Simulador de Voo 3D (F-14 Tomcat)**, bem como as condições de uso e cuidados de distribuição conhecidos na data da última revisão.

> **Última atualização:** `25 de novembro de 2026`.
>
> Este documento é um registro de proveniência e uma orientação de conformidade para o projeto acadêmico; não substitui os contratos/licenças originais nem constitui aconselhamento jurídico. A licença aplicável é a versão vigente na data do download de cada recurso. Guarde cópias das licenças, páginas dos arquivos e comprovantes de download.

---

## 1. Sons ambientes — Sonniss #GameAudioGDC 2026

**Origem:** [Sonniss — GDC 2026 Game Audio Bundle](https://gdc.sonniss.com/)  
**Licença:** [#GameAudioGDC Bundle License](https://sonniss.com/gdc-bundle-license/)  
**Pacote/biblioteca:** Sonniss #GameAudioGDC 2026.

### Arquivos utilizados

| Arquivo no projeto | Arquivo original no bundle | Biblioteca de origem | Uso no TOP GRAPHICS |
|---|---|---|---|
| `assets/audio/ambience/scene1.mp3` | `WATRWave_Soft Waves Cliffs_JSE_RCoN_Stereo.wav` | `Rocky Coast of Norway` (`JSE_RCoN`) | Ambiente de ondas marítimas na Cena 1 (Oceano / Porta-Aviões CVN-65) |
| `assets/audio/ambience/scene2.mp3` | `WINDDsgn_EXT, Eye Of The Storm_344 Audio_Extreme Winds Vol 1.wav` | `Extreme Winds Vol. 1` — 344 Audio | Ambiente de ventos intensos na Cena 2 (Cânion Procedural) |

*(Os arquivos originais `.wav` de alta taxa de amostragem foram mantidos fora do controle de versão via `.gitignore` e convertidos para `.mp3` com janela de loop estável para otimização de tamanho e inicialização do simulador.)*

### Condições relevantes da licença Sonniss

A licença publicada para o bundle concede licença mundial, não exclusiva e livre de royalties (versão 2.0 vigente a partir de **27 de agosto de 2026**; versão 1.0 vigente de 28/01/2024 a 26/08/2026):

- Permite usar e modificar os efeitos em projetos pessoais e comerciais, sem obrigação de atribuição ao criador original.
- Permite sincronizar os efeitos com projetos audiovisuais e interativos (jogos, simuladores e aplicações multimídia).
- Permite compartilhar os efeitos com integrantes da equipe envolvidos no projeto.
- **Não permite distribuir, publicar, sublicenciar ou fornecer os efeitos como arquivos de áudio independentes (*standalone*)** a terceiros sem autorização prévia e escrita da Sonniss (inclusive versões modificadas ou convertidas).
- O projeto finalizado pode ser compartilhado quando os sons estiverem incorporados e sincronizados ao programa, não sendo ofertados como banco de áudio isolado.
- Proíbe o uso dos efeitos para treinamento ou desenvolvimento de tecnologias de inteligência artificial.

---

## 2. Efeitos sonoros da aeronave — FS2004 Grumman F-14 Tomcat Sound Pack

**Pacote:** `FS2004 Grumman F-14 Tomcat Sound Pack` (`f14ge110.zip`)  
**Página de origem:** [Fly Away Simulation — FS2004 Grumman F-14 Tomcat Sound Pack](https://flyawaysimulation.com/downloads/files/2910/fs2004-grumman-f-14-tomcat-sound-pack/)  
**Termos da plataforma:** [Fly Away Simulation — Terms of Use & Privacy Policy](https://flyawaysimulation.com/terms-privacy/)

A página do pacote informa que os **sons dos motores foram gravados e editados por Christoffer Petersen**, juntamente com outros efeitos de cabine e mecânica (também referenciados no cabeçalho do `Sound.cfg` original).

### Recursos ativos no TOP GRAPHICS (`assets/audio/aircraft/`)

| Subpasta | Arquivos ativos no mixer (`audio_config.py`) | Uso no TOP GRAPHICS |
|---|---|---|
| `interior/` | `A_f14_0.wav`–`A_f14_3.wav`, `B_f14_0.wav`–`B_f14_3.wav`, `A_COMB_1.wav`–`A_COMB_4.wav`, `B_COMB_1.wav`–`B_COMB_4.wav`, `A_EFSC.wav`, `B_EFSC.wav` | Motores 1 e 2 (*Jet Whine*, *Combustion* e *Afterburner* `EFSC`) na perspectiva interna (Câmera 2 — Cockpit) |
| `exterior/` | `X_A_f14_0.wav`–`X_A_f14_3.wav`, `X_B_f14_0.wav`–`X_B_f14_3.wav`, `X_A_COMB_1.wav`–`X_A_COMB_4.WAV`, `X_B_COMB_1.wav`–`X_B_COMB_4.WAV`, `X_A_EFSC.wav`, `X_B_EFSC.wav` | Motores 1 e 2 e *Afterburner* na perspectiva externa (Câmeras 1 e 3) |
| `events/` | `T_f14_START.wav`, `X_T_f14_START.wav`, `T_COMB_START.wav`, `X_T_COMB_START.wav`, `T_COMB_SHUT.wav`, `X_T_f14_SHUT.wav` | Partida, ignição de combustão e corte de turbina (recortados e filtrados em passa-baixas) |
| `events/` | `GEARDOWN.wav`, `GEARUP.wav` | Acionamento e recolhimento do trem de pouso retrátil (concatenados com *Time-Stretch OLA* para `1.22 s`) |
| `events/` | `FLAPS.wav` | Atuador hidráulico dos **Trailing-Edge Flaps** (`speed=1.0`) e reaproveitado em canal independente (`speed=1.18`) para os **Split Air Brakes** |
| `events/` | `touchc.wav`, `roll2.wav` | Contato das rodas no pouso (*touchdown*) e rolagem sobre o convés do CVN-65 (*ground roll*) |

### Crédito e observação de licenciamento

- **Crédito:** Pacote `FS2004 Grumman F-14 Tomcat Sound Pack` (`f14ge110.zip`), disponibilizado via Fly Away Simulation; sons dos motores gravados e editados por **Christoffer Petersen**.
- **Atenção sobre "Freeware":** Os termos da Fly Away Simulation estabelecem que cada arquivo *freeware* permanece sujeito aos direitos autorais e restrições do respectivo autor (especialmente quanto a uso comercial e redistribuição). Antes de qualquer distribuição comercial ou pública fora do escopo acadêmico, consulte integralmente os arquivos `read me.txt` e `flyawaysimulation.txt` do pacote original e, se necessário, obtenha autorização expressa do titular.

---

## 3. Efeitos sonoros de colisões e interface — Pixabay

**Fonte:** [Pixabay Sound Effects](https://pixabay.com/sound-effects/)  
**Licença:** [Pixabay Content License — Terms of Service](https://pixabay.com/service/terms/) e [Resumo da Licença](https://pixabay.com/service/license-summary/).

### Arquivos utilizados

| Arquivo no projeto | Título na fonte | Página individual | Uso no TOP GRAPHICS |
|---|---|---|---|
| `assets/audio/aircraft/events/boom_crash.wav` | Horror Boom Crash | [Pixabay — 487664](https://pixabay.com/sound-effects/horror-boom-crash-487664/) | Impacto/explosão em colisões sólidas (navio, convés, cânion, rochas, bunker) e base grave em colisões aquáticas |
| `assets/audio/aircraft/events/water_splash.wav` | Nature Water Splash Effect | [Pixabay — 443133](https://pixabay.com/sound-effects/nature-water-splash-effect-443133/) | Camada simultânea de *splash* em colisões com as ondas físicas do oceano (Cena 1) |
| `assets/audio/menu/menu1.wav` | Menu Click | [Pixabay — 147357](https://pixabay.com/sound-effects/film-special-effects-menu-click-147357/) | Confirmação/seleção de opção nos menus (`MENU_SFX_MAP["select"]`) |
| `assets/audio/menu/menu2.wav` | UI Sound | [Pixabay — 374228](https://pixabay.com/sound-effects/film-special-effects-ui-sound-374228/) | Navegação entre itens e ajuste de sliders de volume (`MENU_SFX_MAP["move"]`) |
| `assets/audio/menu/menu3.wav` | UI Close SFX | [Pixabay — 513359](https://pixabay.com/sound-effects/technology-ui-close-sfx-513359/) | Abertura e fechamento do Menu de Pause (`MENU_SFX_MAP["pause"]`) |

### Condições relevantes da licença Pixabay

A Pixabay Content License permite baixar, usar, modificar e incorporar os arquivos de áudio em projetos comerciais e não comerciais (incluindo jogos e aplicações) sem exigência de atribuição, sendo vedada apenas a venda ou redistribuição isolada (*standalone*) dos arquivos originais como pacote de efeitos sonoros.

---

## 4. Trilhas musicais

As trilhas musicais foram integradas ao gerenciador (`AudioManager.set_music_context`) com *crossfade* suave de `1.5 s` entre o contexto de menus/inspeção e o contexto de voo.

| Arquivo no projeto | Contexto no simulador | Título / Faixa | Fonte individual | Status de licença |
|---|---|---|---|---|
| `assets/audio/music/menu_inspection.mp3` | Menu Principal e Cena 3 (Hangar de Inspeção) | **Gamer Menu** | [Pixabay — 431351](https://pixabay.com/pt/music/jogos-de-v%C3%ADdeo-gamer-menu-431351/) | Pixabay Content License (uso incorporado permitido; não distribuir como arquivo isolado) |
| `assets/audio/music/flight.mp3` | Cenas 1 (Oceano / CVN-65) e 2 (Cânion) | **Danger Zone (Instrumental Version)** — *Hit Crew Masters* | [mp3.pm — 76653820](https://412284-hit-crew-masters.mp3.pm/song/76653820-danger-zone-instrumental-version/) | **Atenção — obra protegida por direitos autorais** (uso estritamente acadêmico/demonstrativo) |

### Observação importante sobre `flight.mp3`

A composição *Danger Zone* (originalmente interpretada por Kenny Loggins na trilha de *Top Gun*, aqui em versão instrumental atribuída a *Hit Crew Masters*) é uma obra musical protegida por direitos autorais de terceiros e **não** é licenciada sob licença livre/royalty-free.

- Seu uso neste repositório tem caráter **estritamente educacional e demonstrativo** na disciplina de Computação Gráfica.
- Caso o projeto venha a ser distribuído comercialmente ou publicado em plataformas sujeitas a reivindicação de direitos autorais (*Content ID* / *DMCA*), substitua `assets/audio/music/flight.mp3` por uma faixa livre de royalties (por exemplo, da biblioteca do Pixabay). Como o campo `"optional": True` está ativo em `audio_config.py`, o simulador também executa normalmente mesmo na ausência do arquivo `.mp3`.

---

## 5. Boas práticas de manutenção e distribuição

- Manter este documento sincronizado com `src/audio_config.py` e com a seção **Créditos e Assets** do `README.md` sempre que um recurso sonoro for adicionado, substituído ou removido.
- Não publicar os arquivos `.wav` ou `.mp3` de terceiros como pacote de áudio independente (*standalone*).
- Respeitar os direitos dos autores originais e substituir recursos sem licença de redistribuição aberta antes de qualquer distribuição comercial.

---

## 6. Fontes e referências

1. **Sonniss — GDC 2026 Game Audio Bundle:** <https://gdc.sonniss.com/>
2. **Sonniss — #GameAudioGDC Bundle License:** <https://sonniss.com/gdc-bundle-license/>
3. **Fly Away Simulation — FS2004 Grumman F-14 Tomcat Sound Pack:** <https://flyawaysimulation.com/downloads/files/2910/fs2004-grumman-f-14-tomcat-sound-pack/>
4. **Fly Away Simulation — Terms of Use & Privacy Policy:** <https://flyawaysimulation.com/terms-privacy/>
5. **Pixabay — Content License / Terms of Service:** <https://pixabay.com/service/terms/>
6. **Pixabay — Content License Summary:** <https://pixabay.com/service/license-summary/>
7. **Pixabay Music — Gamer Menu:** <https://pixabay.com/pt/music/jogos-de-v%C3%ADdeo-gamer-menu-431351/>
8. **Danger Zone (Instrumental Version) — Hit Crew Masters:** <https://412284-hit-crew-masters.mp3.pm/song/76653820-danger-zone-instrumental-version/>
9. **Pixabay SFX — Horror Boom Crash:** <https://pixabay.com/sound-effects/horror-boom-crash-487664/>
10. **Pixabay SFX — Nature Water Splash Effect:** <https://pixabay.com/sound-effects/nature-water-splash-effect-443133/>
11. **Pixabay SFX — Menu Click:** <https://pixabay.com/sound-effects/film-special-effects-menu-click-147357/>
12. **Pixabay SFX — UI Sound:** <https://pixabay.com/sound-effects/film-special-effects-ui-sound-374228/>
13. **Pixabay SFX — UI Close SFX:** <https://pixabay.com/sound-effects/technology-ui-close-sfx-513359/>