import sys; sys.path.insert(0,'/home/claude/fe4/tools')
from emu import Emu, BTN
from PIL import Image
def hold(e,b,n=20,after=120):
    e.held={BTN[x] for x in (b if isinstance(b,list) else [b])}; e.run(n); e.held=set(); e.run(after)
def grid(paths,out,cols=4):
    ims=[Image.open(p) for p in paths]
    rows=(len(ims)+cols-1)//cols
    W=Image.new('RGB',(256*cols,224*rows))
    for i,im in enumerate(ims): W.paste(im,((i%cols)*256,(i//cols)*224))
    W.save(out)
