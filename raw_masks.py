from pathlib import Path
import json

import av
import numpy as np
from PIL import Image
import requests

def segment_raw(video,folder,prompt='person'):
    """Use Fal's mask-applied SAM 3 video to produce reviewable raw PNG masks."""
    from fal_service import download,file_url,run,upload
    folder=Path(folder)
    source_url=upload(video)
    data,request_id=run('fal-ai/sam-3/video',{'video_url':source_url,'prompt':prompt,'apply_mask':True,'video_output_type':'X264 (.mp4)','detection_threshold':0.5},folder,'sam3',print)
    masked=download(file_url(data.get('video')),folder/'sam-mask-applied.mp4')
    out=folder/'raw-masks';out.mkdir(exist_ok=True)
    count=0
    with av.open(str(masked)) as source:
        for index,frame in enumerate(source.decode(video=0)):
            rgba=frame.to_ndarray(format='rgba')
            # Fal's mask-applied output has the non-selected area cleared. Use
            # alpha when present, otherwise retain every non-black output pixel.
            alpha=rgba[:,:,3]
            if np.any(alpha<255):mask=alpha>0
            else:mask=rgba[:,:,:3].max(axis=2)>8
            Image.fromarray((mask.astype(np.uint8)*255),mode='L').save(out/f'mask_{index:05d}.png')
            count+=1
    if not count:raise ValueError('Fal SAM 3 returned an empty mask video.')
    (folder/'sam-raw-request.json').write_text(json.dumps({'provider':'fal','model':'fal-ai/sam-3/video','request_id':request_id,'prompt':prompt,'source':'sam-mask-applied.mp4','mask_count':count},indent=2))
    return out

def clean_border_fragments(folder):
    """Remove tiny, narrow disconnected edge fragments; preserve large edge subjects."""
    import numpy as np
    from PIL import Image
    from scipy.ndimage import label
    folder=Path(folder);output=folder.parent/'clean-masks';output.mkdir(exist_ok=True)
    report=[]
    for p in sorted(folder.glob('mask_*.png')):
        a=np.asarray(Image.open(p).convert('L'))>127;labels,_=label(a);h,w=a.shape;removed=0
        for ident in (set(labels[:,0])|set(labels[:,-1]))-{0}:
            y,x=np.where(labels==ident)
            if len(x)<h*w*.03 and x.max()-x.min()+1<=max(6,int(w*.05)):
                a[labels==ident]=False;removed+=len(x)
        Image.fromarray(a.astype(np.uint8)*255).save(output/p.name)
        report.append({'frame':p.stem,'removed_border_pixels':removed,'mask_pixels':int(a.sum()),'left_right_edge_pixels':int(a[:,0].sum()+a[:,-1].sum())})
    (folder.parent/'mask-cleanup-report.json').write_text(json.dumps(report,indent=2))
    return output
