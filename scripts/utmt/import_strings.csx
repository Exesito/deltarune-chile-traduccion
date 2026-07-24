// import_strings.csx
// -----------------------------------------------------------------------------
// Reescribe strings del pool de un data.win con la traduccion, por INDICE.
//
// Se corre headless con UndertaleModCli:
//   DR_IN=/ruta/strings_cl.json \
//   UndertaleModCli load chapterN/data.win --scripts import_strings.csx \
//                        --output chapterN/data_cl.win
//
// Entrada (JSON) -- el mismo formato que produce el builder:
//   { "strings": { "<indice_en_el_pool>": "<texto_traducido>", ... } }
//   (tambien acepta un objeto plano { "<indice>": "<texto>", ... })
//
// SEGURIDAD: nunca reescribe un string que ademas se usa como NOMBRE interno
// (de code, script, objeto, sprite, room, sonido, fuente, variable, funcion...),
// porque eso renombraria assets y romperia el juego. Esos se saltan con aviso.
// -----------------------------------------------------------------------------

using System;
using System.IO;
using System.Text.Json;
using System.Collections.Generic;
using UndertaleModLib.Models;

string inPath = Environment.GetEnvironmentVariable("DR_IN");
if (string.IsNullOrEmpty(inPath))
    throw new Exception("Falta la variable de entorno DR_IN con la ruta del strings_cl.json");
if (!File.Exists(inPath))
    throw new Exception($"No existe el archivo de entrada: {inPath}");

// --- 1) leer traduccion {indice: texto} ------------------------------------
var translations = new Dictionary<int, string>();
using (var doc = JsonDocument.Parse(File.ReadAllText(inPath)))
{
    JsonElement root = doc.RootElement;
    JsonElement map = root;
    if (root.ValueKind == JsonValueKind.Object && root.TryGetProperty("strings", out var inner))
        map = inner;
    foreach (var prop in map.EnumerateObject())
    {
        if (prop.Value.ValueKind != JsonValueKind.String) continue;
        if (int.TryParse(prop.Name, out int idx))
            translations[idx] = prop.Value.GetString();
    }
}
Console.WriteLine($"[import_strings] entradas a aplicar: {translations.Count}");

// --- 2) armar set de strings PROTEGIDOS (usados como nombres) ---------------
var protectedStrings = new HashSet<UndertaleString>();
void Protect<T>(IList<T> list) where T : UndertaleNamedResource
{
    if (list == null) return;
    foreach (var it in list)
    {
        try { if (it?.Name != null) protectedStrings.Add(it.Name); } catch { }
    }
}
Protect(Data.Code);
Protect(Data.CodeLocals);
Protect(Data.Scripts);
Protect(Data.Functions);
Protect(Data.Variables);
Protect(Data.GameObjects);
Protect(Data.Sprites);
Protect(Data.Rooms);
Protect(Data.Backgrounds);
Protect(Data.Sounds);
Protect(Data.Paths);
Protect(Data.Fonts);
Protect(Data.Timelines);
Protect(Data.Shaders);
Protect(Data.AudioGroups);
Protect(Data.Extensions);
Console.WriteLine($"[import_strings] strings protegidos (nombres internos): {protectedStrings.Count}");

// --- 3) aplicar ------------------------------------------------------------
int total = Data.Strings.Count;
int applied = 0, skippedProtected = 0, skippedRange = 0, unchanged = 0;
foreach (var kv in translations)
{
    int idx = kv.Key;
    string newText = kv.Value ?? "";
    if (idx < 0 || idx >= total) { skippedRange++; continue; }
    var str = Data.Strings[idx];
    if (protectedStrings.Contains(str))
    {
        skippedProtected++;
        Console.WriteLine($"[import_strings] AVISO: salto indice {idx} (usado como nombre interno): {str.Content}");
        continue;
    }
    if (str.Content == newText) { unchanged++; continue; }
    str.Content = newText;
    applied++;
}

Console.WriteLine($"[import_strings] aplicados={applied}  sin_cambio={unchanged}  " +
                  $"saltados_protegidos={skippedProtected}  fuera_de_rango={skippedRange}");
