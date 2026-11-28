/* Testes do parser de playlist M3U (sem dependências).
   Rode na raiz do repositório:
     node web/tools/testar-playlist.js
*/
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const arquivo = path.join(__dirname, "..", "app", "assets", "js", "playlist.js");
const codigo = fs.readFileSync(arquivo, "utf8");
const sandbox = { window: {}, console, TextDecoder };
vm.runInNewContext(codigo, sandbox, { filename: arquivo });
const playlist = sandbox.window.EFTV_PLAYLIST;

const EXEMPLO = `#EXTM3U
#EXTINF:-1 tvg-id="globo.br" tvg-name="Globo" tvg-logo="https://cdn.example.com/globo.png" group-title="Canais | Abertos",Globo HD
https://example.com/live/globo.m3u8
#EXTINF:-1 tvg-logo="The-Walking-Dead.png" tvg-logo="https://cdn.example.com/twd.png" group-title="Séries | Drama",The Walking Dead S01E01 Days Gone Bye
https://example.com/vod/twd-s01e01.mp4
#EXTINF:-1 tvg-logo="https://cdn.example.com/twd.png" group-title="Séries | Drama",The Walking Dead S01E02 Guts
https://example.com/vod/twd-s01e02.mp4
#EXTINF:-1 group-title="Filmes | Ação",John Wick 4
https://example.com/vod/john-wick-4.mkv
#EXTINF:-1 group-title="Canais | Esportes",Sportv
https://example.com/live/sportv.m3u8
#EXTINF:-1 group-title="Filmes | Adultos",Filme Adulto
https://example.com/vod/adulto.mp4
#EXTINF:-1 group-title="Canais | Notícias",CNN Brasil
rtmp://example.com/cnn
#EXTINF:-1 group-title="Séries | Drama",Série Solta
https://example.com/vod/serie-solta.mp4
`;

let passou = 0;
function teste(nome, fn) {
  try {
    fn();
    passou += 1;
    console.log("ok - " + nome);
  } catch (erro) {
    console.error("FALHOU - " + nome);
    console.error(erro && erro.stack ? erro.stack : erro);
    process.exitCode = 1;
  }
}

teste("lê itens, ignora URL não reproduzível e escolhe logo absoluto", () => {
  const itens = playlist.parse(EXEMPLO);
  assert.strictEqual(itens.length, 7);
  assert.strictEqual(itens[0].name, "Globo HD");
  assert.strictEqual(itens[0].tipo, "canal");
  assert.strictEqual(itens[0].logo, "https://cdn.example.com/globo.png");

  const twd = itens.find((i) => i.name.includes("S01E01"));
  assert.ok(twd);
  assert.strictEqual(twd.tipo, "serie");
  assert.strictEqual(twd.logo, "https://cdn.example.com/twd.png");

  const filme = itens.find((i) => i.name === "John Wick 4");
  assert.strictEqual(filme.tipo, "filme");
  assert.strictEqual(filme.streamType, "mp4");

  assert.ok(!itens.some((i) => i.name === "CNN Brasil"), "rtmp deve ser ignorado");
});

teste("classifica grupos e conteúdo adulto", () => {
  assert.strictEqual(playlist.classificar("Canais | Esportes", "Sportv", "https://x/a.m3u8"), "canal");
  assert.strictEqual(playlist.classificar("Filmes | Ação", "John Wick", "https://x/a.m3u8"), "filme");
  assert.strictEqual(playlist.classificar("Séries | Drama", "The Walking Dead S01E01", "https://x/a.m3u8"), "serie");
  assert.strictEqual(playlist.categoriaDoGrupo("Filmes | Ação", "filme"), "filmes");
  assert.strictEqual(playlist.categoriaDoGrupo("Canais | Esportes", "canal"), "esportes");
  assert.strictEqual(playlist.categoriaDoGrupo("Séries | Anime", "serie"), "series");
  assert.strictEqual(playlist.ehAdulto("Filmes | Adultos", "Filme Adulto"), true);
  assert.strictEqual(playlist.ehAdulto("Canais | Abertos", "Globo"), false);
});

teste("lê temporada/episódio em formatos diferentes", () => {
  const a = playlist.parseSeries("The Walking Dead S01E02 Guts");
  assert.deepStrictEqual(
    { title: a.title, season: a.season, episode: a.episode, episodeTitle: a.episodeTitle },
    { title: "The Walking Dead", season: 1, episode: 2, episodeTitle: "Guts" }
  );

  const b = playlist.parseSeries("Casa 2x07");
  assert.strictEqual(b.title, "Casa");
  assert.strictEqual(b.season, 2);
  assert.strictEqual(b.episode, 7);

  const c = playlist.parseSeries("Série X - Temporada 2 Episódio 5");
  assert.strictEqual(c.title, "Série X");
  assert.strictEqual(c.season, 2);
  assert.strictEqual(c.episode, 5);

  const d = playlist.parseSeries("Série X Episódio 3");
  assert.strictEqual(d.season, 1);
  assert.strictEqual(d.episode, 3);

  assert.strictEqual(playlist.parseSeries("John Wick 4"), null);
});

teste("agrupa episódios em um card de série", () => {
  const itens = playlist.parse(EXEMPLO);
  const dados = playlist.montarCatalogo(itens);
  const serie = dados.canais.find((c) => c.nome === "The Walking Dead");

  assert.ok(serie, "card da série deve existir");
  assert.strictEqual(serie.tipo, "serie");
  assert.strictEqual(serie.temporadas, 1);
  assert.strictEqual(serie.totalEpisodios, 2);
  assert.strictEqual(serie.episodios.map((e) => e.episodio).join(","), "1,2");
  assert.strictEqual(serie.episodios[0].temporada, 1);
  assert.ok(serie.episodios[0].nome.includes("T1 E1"));

  const solta = dados.canais.find((c) => c.nome === "Série Solta");
  assert.ok(solta);
  assert.strictEqual(solta.episodios.length, 0, "série sem marcador fica solta");

  assert.strictEqual(dados.canais.filter((c) => c.tipo === "serie").length, 2);
  assert.strictEqual(dados.canais.filter((c) => c.tipo === "filme").length, 2);
  assert.strictEqual(dados.canais.filter((c) => c.tipo === "canal").length, 2);
});

teste("gera categorias, contagens e slugs únicos", () => {
  const dados = playlist.montarCatalogo(playlist.parse(EXEMPLO));
  const ids = dados.categorias.map((c) => c.id);
  assert.ok(ids.includes("todos"));
  assert.ok(ids.includes("series"));
  assert.ok(ids.includes("filmes"));
  assert.ok(ids.includes("esportes"));
  assert.ok(ids.includes("abertos"));

  const series = dados.categorias.find((c) => c.id === "series");
  assert.strictEqual(series.total, 2);

  const slugs = dados.canais.map((c) => c.slug);
  assert.strictEqual(new Set(slugs).size, slugs.length, "slugs devem ser únicos");
  assert.ok(slugs.every((s) => /^[a-z0-9-]+$/.test(s)));
});

teste("tolera playlist vazia ou inválida", () => {
  assert.strictEqual(playlist.parse("").length, 0);
  assert.strictEqual(playlist.parse("<!DOCTYPE html><html></html>").length, 0);
  const dados = playlist.montarCatalogo([]);
  assert.strictEqual(dados.canais.length, 0);
  assert.strictEqual(dados.categorias.length, 1);
  assert.strictEqual(dados.categorias[0].id, "todos");
});

const EXEMPLO_HEADERS = `#EXTM3U
#EXTINF:-1 group-title="Canais | Esportes",Canal Header
#EXTVLCOPT:http-user-agent=Agente/1.0
#EXTVLCOPT:http-referrer=https://ref.example/
https://example.com/live/header.m3u8
#EXTINF:-1 group-title="Canais | Filmes",Canal URL Header
https://example.com/live/url.m3u8|User-Agent=Outro/2.0&Referer=https://ref2.example/
#KODIPROP:inputstream.adaptive.manifest_type=dash
#EXTINF:-1 group-title="Filmes | Ação",Filme DASH
https://example.com/vod/filme.mpd
#EXTINF:-1 group-title="Canais | Filmes",Filme TS
https://example.com/live/12345.ts
`;

teste("lê #EXTVLCOPT, #KODIPROP e headers embutidos na URL", () => {
  const itens = playlist.parse(EXEMPLO_HEADERS);
  assert.strictEqual(itens.length, 4);

  assert.strictEqual(itens[0].headers["User-Agent"], "Agente/1.0");
  assert.strictEqual(itens[0].headers.Referer, "https://ref.example/");
  assert.strictEqual(itens[0].streamType, "hls");

  assert.strictEqual(itens[1].headers["User-Agent"], "Outro/2.0");
  assert.strictEqual(itens[1].headers.Referer, "https://ref2.example/");

  assert.strictEqual(itens[2].streamType, "dash");
  assert.strictEqual(itens[3].streamType, "ts");
  assert.strictEqual(itens[3].tipo, "filme", "Canais | Filmes deve ser filme");
});

teste("processa playlist linha a linha (streaming)", () => {
  const parser = playlist.criarParser();
  EXEMPLO.split(/\r?\n/).forEach((linha) => parser.processarLinha(linha));
  const resultado = parser.finalizar();
  assert.strictEqual(resultado.itens.length, 7);
  assert.ok(resultado.linhas > 10);
  assert.strictEqual(resultado.truncado, false);
});

(async () => {
  try {
    const resposta = new Response(EXEMPLO, {
      status: 200,
      headers: { "Content-Type": "audio/x-mpegurl" },
    });
    const resultado = await playlist.parseResposta(resposta);
    assert.strictEqual(resultado.itens.length, 7);
    assert.ok(resultado.amostra.includes("#EXTM3U"));
    console.log("ok - lê Response em streaming");
    passou += 1;
  } catch (erro) {
    console.error("FALHOU - lê Response em streaming");
    console.error(erro && erro.stack ? erro.stack : erro);
    process.exitCode = 1;
  }
  console.log(`\n${passou} teste(s) passaram.`);
})();
