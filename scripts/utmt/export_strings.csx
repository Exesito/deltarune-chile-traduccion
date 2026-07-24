// export_strings.csx
// -----------------------------------------------------------------------------
// Exporta el pool de strings de un data.win (GameMaker) a JSON, filtrando SOLO
// los candidatos a DIALOGO por heuristica de codigos de control de Deltarune.
//
// Se corre headless con UndertaleModCli:
//   DR_OUT=/ruta/strings_en.json \
//   UndertaleModCli load chapterN/data.win --scripts export_strings.csx
//
// Salida (JSON):
//   {
//     "count": <total de strings en el pool>,
//     "candidates": <cuantos pasaron la heuristica>,
//     "strings": { "<indice_en_el_pool>": "<contenido>", ... }
//   }
//
// La CLAVE es el indice del string en Data.Strings: import_strings.csx lo usa
// para reescribir exactamente ese string. Por eso este archivo queda "casado"
// con la version del data.win del que se exporto (se fija por sha256 aguas abajo).
// -----------------------------------------------------------------------------

using System;
using System.IO;
using System.Text;
using System.Collections.Generic;

// Codigos de control de GameMaker/Deltarune. Si un string los contiene, es casi
// seguro dialogo/UI y NO un identificador interno.
bool LooksLikeDialogue(string s)
{
    if (string.IsNullOrEmpty(s)) return false;

    // 1) Codigos de control tipicos de dialogo: & (salto), % (fin), ^ (pausa)
    if (s.IndexOf('&') >= 0 || s.IndexOf('%') >= 0 || s.IndexOf('^') >= 0)
        return true;

    // 2) Secuencias con backslash: \cX color, \M cara, \E emocion, \R, \s, \T ...
    for (int i = 0; i + 1 < s.Length; i++)
    {
        if (s[i] == '\\')
        {
            char c = s[i + 1];
            if ("cCmMeErRsStTfFzZ".IndexOf(c) >= 0) return true;
        }
    }

    // 3) Lenguaje natural: tiene espacio, al menos una letra, y NO parece un
    //    identificador/ruta/archivo interno de GameMaker.
    bool hasSpace = s.IndexOf(' ') >= 0;
    bool hasLetter = false;
    foreach (char c in s) { if (char.IsLetter(c)) { hasLetter = true; break; } }
    if (!hasSpace || !hasLetter) return false;

    // descarta identificadores tipo gml_Object_..., rutas, snake_case, urls
    if (s.StartsWith("gml_") || s.StartsWith("gui_") || s.StartsWith("obj_") ||
        s.StartsWith("spr_") || s.StartsWith("snd_") || s.StartsWith("mus_"))
        return false;
    if (s.IndexOf('/') >= 0 || s.IndexOf('\\') >= 0) return false;       // rutas
    if (s.IndexOf("://") >= 0) return false;                              // urls
    if (s.IndexOf('.') >= 0 && s.IndexOf(' ') < 0) return false;          // archivo.ext

    return true;
}

// Escapado JSON minimo y correcto (sin depender de librerias externas).
void AppendJsonString(StringBuilder sb, string s)
{
    sb.Append('"');
    foreach (char c in s)
    {
        switch (c)
        {
            case '"':  sb.Append("\\\""); break;
            case '\\': sb.Append("\\\\"); break;
            case '\b': sb.Append("\\b");  break;
            case '\f': sb.Append("\\f");  break;
            case '\n': sb.Append("\\n");  break;
            case '\r': sb.Append("\\r");  break;
            case '\t': sb.Append("\\t");  break;
            default:
                if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                else sb.Append(c);
                break;
        }
    }
    sb.Append('"');
}

string outPath = Environment.GetEnvironmentVariable("DR_OUT");
if (string.IsNullOrEmpty(outPath)) outPath = "strings_en.json";

int total = Data.Strings.Count;
var sb = new StringBuilder();
sb.Append("{\n");
sb.Append("  \"count\": ").Append(total).Append(",\n");

int candidates = 0;
var body = new StringBuilder();
for (int i = 0; i < total; i++)
{
    string content = Data.Strings[i]?.Content;
    if (!LooksLikeDialogue(content)) continue;
    if (candidates > 0) body.Append(",\n");
    body.Append("    \"").Append(i).Append("\": ");
    AppendJsonString(body, content);
    candidates++;
}

sb.Append("  \"candidates\": ").Append(candidates).Append(",\n");
sb.Append("  \"strings\": {\n");
sb.Append(body);
sb.Append("\n  }\n}\n");

File.WriteAllText(outPath, sb.ToString(), new UTF8Encoding(false));
Console.WriteLine($"[export_strings] pool total={total}  candidatos a dialogo={candidates}");
Console.WriteLine($"[export_strings] escrito -> {outPath}");
