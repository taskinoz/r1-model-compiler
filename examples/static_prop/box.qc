$modelname "r1c_examples/box.mdl"
$cdmaterials ""
$body "body" "box.smd"
$staticprop
$surfaceprop "metal"
$sequence "idle" "box.smd"
$collisionmodel "box.smd" { $mass 50 }
