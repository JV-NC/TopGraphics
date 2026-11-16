# Créditos e licenças de áudio — TOP GRAPHICS

Este documento registra as fontes dos efeitos sonoros e das trilhas musicais utilizados no **TOP GRAPHICS — Simulador de Voo 3D (F-14 Tomcat)**, bem como as condições de uso conhecidas na data da última revisão.

> **Última verificação das páginas de licença: 15 de novembro de 2026.**
>
> Este documento é um registro de proveniência e uma orientação de conformidade para o projeto; não substitui os contratos/licenças originais nem constitui aconselhamento jurídico. A licença aplicável é a versão aceita na data do download de cada recurso. Guarde cópias das licenças, páginas dos arquivos e comprovantes de download.

---

## 1. Efeitos sonoros — Sonniss #GameAudioGDC 2026

**Origem:** [Sonniss — GDC 2026 Game Audio Bundle](https://gdc.sonniss.com/)  
**Licença:** [#GameAudioGDC Bundle License](https://sonniss.com/gdc-bundle-license/)  
**Pacote/biblioteca:** Sonniss #GameAudioGDC 2026.

### Arquivos utilizados

| Arquivo | Biblioteca de origem indicada no pacote | Uso no TOP GRAPHICS |
|---|---|---|
| `WATRWave_Soft Waves Cliffs_JSE_RCoN_Stereo.wav` | `Rocky Coast of Norway` (identificação `JSE_RCoN` no nome do arquivo) | Ambiente de ondas para a cena do porta-aviões/oceano |
| `WINDDsgn_EXT, Eye Of The Storm_344 Audio_Extreme Winds Vol 1.wav` | `Extreme Winds Vol. 1` — 344 Audio | Ambiente de vento para a cena do cânion |

### Condições relevantes da licença Sonniss

A licença publicada para o bundle concede uma licença mundial, não exclusiva e livre de royalties. A versão 2.0 está indicada como vigente a partir de **27 de agosto de 2026**. Entre as permissões e restrições relevantes para este projeto:

- Permite usar e modificar os efeitos em projetos pessoais e comerciais, sem obrigação de atribuição ao criador original.
- Permite sincronizar os efeitos com projetos audiovisuais e interativos, incluindo jogos, aplicações e projetos multimídia.
- Permite compartilhar os efeitos com integrantes da própria equipe/organização que estejam trabalhando no projeto.
- **Não permite distribuir, publicar, sublicenciar ou fornecer os efeitos como arquivos de áudio** a terceiros sem autorização prévia e escrita da Sonniss. A restrição também abrange sons modificados ou redesenhados e sua inclusão em bibliotecas, pacotes de assets, templates ou SDKs.
- O projeto finalizado pode ser compartilhado/publicado normalmente quando os sons estiverem incorporados e sincronizados ao projeto, e não sendo fornecidos como efeitos sonoros independentes.
- A licença proíbe utilizar os efeitos para treinamento ou desenvolvimento de tecnologias de inteligência artificial.
- Os direitos autorais dos sons continuam pertencendo aos respectivos titulares; a licença concede somente os direitos de uso nela descritos.

A atribuição não é obrigatória pela licença, mas os arquivos são listados aqui para manter a rastreabilidade dos recursos utilizados.

**Atenção à versão da licença:** a Sonniss informa que a versão aplicável é a que estava publicada na data do download. A versão 1.0 esteve em vigor de 28 de janeiro de 2024 até 26 de agosto de 2026; a versão 2.0 entrou em vigor em 27 de agosto de 2026. Confirmar a data efetiva de download do bundle e arquivar a versão correspondente.

---

## 2. Efeitos sonoros — FS2004 Grumman F-14 Tomcat Sound Pack

**Pacote:** `FS2004 Grumman F-14 Tomcat Sound Pack` (`f14ge110.zip`)  
**Página de origem:** [Fly Away Simulation — FS2004 Grumman F-14 Tomcat Sound Pack](https://flyawaysimulation.com/downloads/files/2910/fs2004-grumman-f-14-tomcat-sound-pack/)  
**Termos da plataforma:** [Fly Away Simulation — Terms of Use & Privacy Policy](https://flyawaysimulation.com/terms-privacy/)

A página do pacote informa que os **sons dos motores foram gravados e editados por Christoffer Petersen**, juntamente com outros sons. O arquivo `Sound.cfg` incluído no pacote também contém um cabeçalho atribuído a Christoffer Petersen. A página lista o pacote como freeware e identifica o arquivo ZIP como `f14ge110.zip`.

### Recursos aproveitados/previstos no TOP GRAPHICS

O pacote contém, entre outros, os seguintes arquivos (nomes conforme listagem da página; conferir os arquivos realmente extraídos):

- **Motores — perspectiva interna:** `A_f14_0.wav` a `A_f14_3.wav`, `B_f14_0.wav` a `B_f14_3.wav`, `A_COMB_1.wav` a `A_COMB_4.wav`, `B_COMB_1.wav` a `B_COMB_4.wav`, `A_EFSC.wav` e `B_EFSC.wav`.
- **Motores — perspectiva externa:** versões correspondentes com prefixo `X_`, incluindo `X_A_f14_*`, `X_B_f14_*`, `X_A_COMB_*`, `X_B_COMB_*`, `X_A_EFSC.wav` e `X_B_EFSC.wav`.
- **Partida e desligamento:** `T_f14_START.wav`, `T_COMB_START.wav`, `T_COMB_SHUT.wav` e versões externas `X_T_f14_START.wav`, `X_T_COMB_START.wav` e `X_T_f14_SHUT.wav`.
- **Controles e voo:** `FLAPS.wav`, `GEARDOWN.wav`, `gearup.wav`, `NEWWIND.WAV`, `wind.wav`, `roll1.wav` e `roll2.wav`.
- **Contato com o solo:** `touchl.wav`, `touchc.wav` e `touchr.wav`.

A relação acima documenta a composição divulgada do pacote; não significa que todos os arquivos já estejam ativos na versão atual do simulador.

### Crédito

- **Pacote:** FS2004 Grumman F-14 Tomcat Sound Pack (`f14ge110.zip`), disponibilizado pela Fly Away Simulation.
- **Sons dos motores:** gravados e editados por **Christoffer Petersen**, conforme crédito exibido na página do pacote.
- **Demais efeitos incluídos:** a página informa que há outros sons, mas não identifica individualmente seus autores. Consultar o `read me.txt`, `flyawaysimulation.txt` e eventuais avisos/licenças presentes no arquivo original antes de atribuir autoria ou definir a permissão de uso de cada efeito.

### Situação da licença — confirmação necessária

**Não tratar a indicação “Freeware” como uma licença aberta ou como autorização automática para redistribuir os WAVs.** Os termos atuais da Fly Away Simulation esclarecem que:

- O acesso ao site concede uma licença pessoal, não exclusiva e revogável para baixar arquivos para uso próprio e não comercial em simulação de voo, sujeita às condições do desenvolvedor de cada arquivo.
- Cada arquivo freeware está sujeito à licença própria do desenvolvedor e às notas existentes na página ou dentro do arquivo; devem ser respeitadas, em especial, as restrições de uso comercial e redistribuição.
- A plataforma informa que o copyright dos arquivos normalmente permanece com o desenvolvedor indicado e que o fato de um arquivo estar hospedado no site não transfere o copyright à Fly Away Simulation.
- A página do pacote recomenda consultar o `readme` incluído, que é a referência específica para as instruções e condições daquele arquivo.

Com as informações públicas consultadas, **não foi possível confirmar uma autorização expressa para redistribuir os sons desse pacote junto ao TOP GRAPHICS, publicar os WAVs em um repositório público ou sublicenciá-los**. O uso local no desenvolvimento não deve ser confundido com autorização para distribuição pública.

**Providências antes de publicar ou distribuir o projeto:**

1. Conferir integralmente o `read me.txt` e o `flyawaysimulation.txt` do ZIP original e guardar cópias no registro interno de licenças.
2. Verificar se esses arquivos identificam uma licença específica, restrições de modificação/sincronização ou condições adicionais para os sons de terceiros.
3. Se não houver autorização clara para incorporar e distribuir os sons em outro simulador, solicitar autorização escrita ao titular dos direitos — começando pelo contato do desenvolvedor informado no material original — explicando que os áudios serão editados/recortados, sincronizados ao TOP GRAPHICS e eventualmente incluídos em uma distribuição acadêmica do programa.
4. Até obter confirmação, manter esses WAVs fora de repositórios públicos e de pacotes distribuídos a terceiros. Se necessário, manter os arquivos apenas no ambiente local de desenvolvimento e preparar uma versão distribuível sem esses recursos.

A atribuição de crédito é mantida por transparência, mas **crédito não substitui autorização de uso ou redistribuição**.

---

## 3. Trilha sonora — placeholders e possíveis faixas Pixabay

**Status atual:** as trilhas sonoras estão representadas por placeholders. Nenhuma faixa específica do Pixabay está registrada como recurso efetivamente utilizado nesta versão.

**Fonte planejada:** [Pixabay Music — Cinematic](https://pixabay.com/music/search/cinematic/) e outras categorias da biblioteca, conforme a necessidade de cada cena.  
**Licença:** [Pixabay Content License — Terms of Service](https://pixabay.com/service/terms/) e [resumo da licença](https://pixabay.com/service/license-summary/).

### Organização musical prevista

| Contexto | Trilha prevista | Status |
|---|---|---|
| Menu principal (a implementar) e cena de inspeção/hangar | Trilha cinematográfica/ambiente mais contemplativa | Placeholder — faixa ainda não selecionada |
| Cena de voo 1 — porta-aviões/oceano | Trilha de voo | Placeholder — faixa ainda não selecionada |
| Cena de voo 2 — cânion | Trilha de voo | Placeholder — faixa ainda não selecionada |

A ideia é utilizar uma trilha compartilhada entre os dois cenários de voo e outra para o menu principal e a cena de inspeção, com controle de volume e transição conforme a mudança de estado/cena.

### Condições relevantes da licença Pixabay

Na versão dos termos consultada em **15 de novembro de 2026**, a licença de conteúdo do Pixabay permite, em linhas gerais, baixar, usar, copiar, modificar e adaptar o conteúdo para fins comerciais ou não comerciais, sem obrigação de atribuição.

A principal restrição relevante ao TOP GRAPHICS é a proibição de vender ou distribuir o conteúdo de forma isolada (*standalone*). A licença diferencia o arquivo original — ou uma alteração mínima que continue essencialmente igual — de seu uso incorporado a uma criação maior, como um aplicativo ou jogo. O Pixabay também recomenda verificar direitos de terceiros eventualmente associados ao conteúdo.

A atribuição não é obrigatória, mas é recomendável registrar cada faixa usada. Antes de incorporar uma música, verificar a página individual da faixa e salvar o link, o nome do criador e a prova/registro da licença disponível na data do download. Os termos do Pixabay podem ser atualizados; conferir a versão vigente no momento de cada obtenção.

### Modelo para registrar futuras faixas

Adicionar uma linha por faixa efetivamente baixada:

| Uso no projeto | Título da faixa | Criador | Página individual | Data do download | Licença/prova |
|---|---|---|---|---|---|
| Menu + inspeção | `A preencher` | `A preencher` | `URL da faixa` | `AAAA-MM-DD` | Pixabay Content License — guardar comprovante |
| Voo — cenas 1 e 2 | `A preencher` | `A preencher` | `URL da faixa` | `AAAA-MM-DD` | Pixabay Content License — guardar comprovante |

**Não usar apenas o link de uma busca/categoria como crédito final.** O registro deve apontar para a página individual de cada faixa selecionada.

---

## 4. Boas práticas de distribuição e manutenção

- Manter este arquivo atualizado sempre que um áudio for adicionado, substituído ou removido.
- Registrar o nome original do arquivo, a biblioteca/pacote de origem, o autor quando identificado, a URL de origem, a data do download e a licença aplicável.
- Guardar cópias das licenças e dos `readme` originais em um local interno de documentação, sem republicar materiais protegidos.
- Não assumir que a autorização de uma biblioteca se aplica a outra: cada faixa deve ser associada à sua fonte e licença específicas.
- Não publicar WAVs originais ou recortados como pacote de áudio independente.
- Antes de publicar o repositório, verificar os arquivos rastreados pelo Git. Para recursos cuja redistribuição não esteja autorizada, manter os assets fora do repositório público e documentar como obtê-los legalmente.
- Distinguir no código e na documentação os placeholders, os recursos já integrados e os recursos cuja licença ainda está pendente de confirmação.

### Exemplo de referência no README principal

```markdown
## Créditos de áudio

As fontes, os autores identificados e as informações de licenciamento dos efeitos sonoros e das trilhas utilizadas estão documentados em [audio_credits.md](audio_credits.md).

Os arquivos de áudio de terceiros permanecem sujeitos às respectivas licenças. Consulte esse documento antes de redistribuir o projeto ou seus assets.
```

---

## 5. Fontes consultadas

1. **Sonniss — GDC 2026 Game Audio Bundle:** <https://gdc.sonniss.com/>
2. **Sonniss — #GameAudioGDC Bundle License:** <https://sonniss.com/gdc-bundle-license/>
3. **Sonniss — versões anteriores da licença:** <https://sonniss.com/gdc-bundle-license/previous-versions/>
4. **Fly Away Simulation — FS2004 Grumman F-14 Tomcat Sound Pack:** <https://flyawaysimulation.com/downloads/files/2910/fs2004-grumman-f-14-tomcat-sound-pack/>
5. **Fly Away Simulation — Terms of Use & Privacy Policy:** <https://flyawaysimulation.com/terms-privacy/>
6. **Pixabay — Music (busca Cinematic):** <https://pixabay.com/music/search/cinematic/>
7. **Pixabay — Content License / Terms of Service:** <https://pixabay.com/service/terms/>
8. **Pixabay — Content License Summary:** <https://pixabay.com/service/license-summary/>

