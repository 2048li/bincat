## Ocaml
* optim: supprimer les maj de flags entre deux instructions pour ceux qui sont set/undef sans avoir été testés
* gérer les questions "synchrones" avec l'interface IDA pour quand il y a une décision à prendre (trop de branches par exemple) ... utiliser un pipe (attention à Windows) ?
* gérer des chemins UTF-8 dans le .ini ?
* gérer l'ordre des initialisation mémoires dans le .ini pour pouvoir écraser certaines parties déjà initialisées

Bugs:
* Jmp et Return dans les boucles doivent en faire sortir. Attention au directives de default_unroll qui suit un jmp repne et à l'incr de esp après le ret qui doivent tout de même être exec
* caractère échappement des format string est le %
* mettre un message quand code dans rep/repe/repne n'est pas stos/scas/etc.

Hard:
* use a shared data structure to store memory only once for all states
* mem deref with taint in displacement expression
* multiplication when only one operand is tainted

## Plugin IDA
* importer les valeurs concrètes depuis le debugger (mémoire et registres)

## Global
* faire marcher `bincat` sous windows ?
* gérer des diffs de mémoire seulement ? (bcp d'instructions ne touchent pas la mémoire, ça éviterait de perdre du temps à tout réécrire.)
* GDB stub pour l'accès à la mémoire (utile pour les processus qui tournent mais aussi pour les binaires compliqués (relocs etc.))
