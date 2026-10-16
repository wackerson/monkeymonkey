"""Isolate vocals before generation and replace generated sound with entire original source audio."""
from pathlib import Path
import json
import av,numpy as np,requests,shutil,subprocess
RATE=44100
SEEDANCE_REFERENCE_WIDTH=720
SEEDANCE_REFERENCE_HEIGHT=1080
SEEDANCE_MAX_VIDEO_BYTES=50*1024*1024

def read_audio(path):
    parts=[];res=av.AudioResampler(format='fltp',layout='stereo',rate=RATE)
    with av.open(str(path)) as c:
        if not c.streams.audio:raise ValueError('Source has no audio track.')
        for f in c.decode(audio=0):
            parts.extend(x.to_ndarray() for x in res.resample(f))
        parts.extend(x.to_ndarray() for x in res.resample(None))
    return np.concatenate(parts,axis=1)

def write_audio(path,a):
    with av.open(str(path),'w') as out:
        s=out.add_stream('pcm_s16le',rate=RATE);s.layout='stereo'
        for i in range(0,a.shape[1],4096):
            f=av.AudioFrame.from_ndarray(np.ascontiguousarray(a[:,i:i+4096].astype(np.float32)),format='fltp',layout='stereo');f.sample_rate=RATE;f.pts=i
            for p in s.encode(f):out.mux(p)
        for p in s.encode():out.mux(p)

def separate(src,folder,status=print):
    folder=Path(folder)
    if (folder/'audio-manifest.json').exists():return
    status('Audio · extracting original track');original=read_audio(src);write_audio(folder/'original-audio.wav',original)
    from fal_service import file_url, run, upload
    status('Audio · uploading source stem to Fal')
    audio_url=upload(folder/'original-audio.wav')
    status('Audio · Fal Demucs separating vocals and original music')
    # Fal otherwise requests every possible Demucs stem, including guitar and
    # piano, which are unavailable on the faster htdemucs variant.
    data,request_id=run('fal-ai/demucs',{'audio_url':audio_url,'model':'htdemucs','stems':['vocals','drums','bass','other'],'output_format':'wav'},folder,'demucs',status)
    stems={}
    for name,value in data.items():
        if not value:continue
        try:url=file_url(value)
        except ValueError:continue
        r=requests.get(url,timeout=120);r.raise_for_status();p=folder/(name+'.wav');p.write_bytes(r.content);stems[name]=read_audio(p)
    if 'vocals' not in stems or not any(n!='vocals' for n in stems):raise ValueError('Separation returned incomplete stems.')
    music=np.zeros_like(original)
    for name,a in stems.items():
        if name!='vocals':n=min(music.shape[1],a.shape[1]);music[:,:n]+=a[:,:n]
    write_audio(folder/'music.wav',np.clip(music,-1,1))
    (folder/'audio-manifest.json').write_text(json.dumps({'fal_request_id':request_id,'seedance_video':'composite-silent.mp4','seedance_audio':'vocals.wav','final_audio':'upload.mp4 (entire original audio track)','discard_seedance_audio':True,'separation':'Fal Demucs htdemucs; residual music or vocal bleed is possible'},indent=2))

def finish_preview(generated,folder,target=None):
    folder=Path(folder);target=Path(target) if target else folder/'final-preview.mp4'
    # Accommodate a small provider rounding gap without cutting source audio.
    with av.open(str(generated)) as probe, av.open(str(folder/'upload.mp4')) as source:
        stream=probe.streams.video[0]
        vd=float(stream.duration*stream.time_base)
        sd=float(source.duration/av.time_base)
    if 0.25 < sd-vd <= 0.5:
        import subprocess
        padded=folder/'seedance-duration-aligned.mp4'
        from fractions import Fraction
        with av.open(str(generated)) as inp,av.open(str(padded),'w') as out:
            video=inp.streams.video[0];rate=video.average_rate or Fraction(24,1)
            stream=out.add_stream('libx264',rate=rate);stream.width=video.width;stream.height=video.height;stream.pix_fmt='yuv420p';stream.options={'crf':'18'}
            frames=list(inp.decode(video=0));count=round(sd*float(rate))
            for i in range(count):
                f=av.VideoFrame.from_ndarray(frames[min(i,len(frames)-1)].to_ndarray(format='rgb24'),format='rgb24');f.pts=i;f.time_base=1/rate
                for packet in stream.encode(f):out.mux(packet)
            for packet in stream.encode():out.mux(packet)
        (folder/'duration-adjustment.json').write_text(json.dumps({'method':'hold final frame','seconds':sd-vd,'original_audio':'unchanged'}))
        generated=padded
    # Copy original compressed audio packets, preserving the complete source mix.
    with av.open(str(generated)) as inp,av.open(str(folder/'upload.mp4')) as source_audio,av.open(str(target),'w') as out:
        if not source_audio.streams.audio:raise ValueError('Original source has no audio track.')
        video=inp.streams.video[0];audio=source_audio.streams.audio[0]
        vd=float(video.duration*video.time_base) if video.duration else float(inp.duration/av.time_base)
        sd=float(source_audio.duration/av.time_base)
        if abs(vd-sd)>.25:raise ValueError('Generated duration differs from original audio; refusing to trim, loop or stretch it.')
        vs=out.add_stream_from_template(video);astream=out.add_stream_from_template(audio)
        for p in inp.demux(video=0):
            if p.dts is not None:p.stream=vs;out.mux(p)
        for p in source_audio.demux(audio=0):
            if p.dts is not None:p.stream=astream;out.mux(p)
    return target

def prepare_seedance_reference(source, folder):
    """Make a conservative Seedance-compatible MP4 without altering the edit.

    Fal accepts MP4/MOV references only within a narrow resolution and duration
    range.  The preprocessing workflow formerly sent its 540x960 portrait
    intermediate directly, which Fal can reject.  This retains every source
    pixel by fitting it inside a 720x1080 H.264 frame; pillarbox padding is
    intentional and avoids cropping the source camera motion.
    """
    source=Path(source);folder=Path(folder)
    with av.open(str(source)) as inp:
        stream=inp.streams.video[0]
        duration=float(inp.duration/av.time_base)
        if not 2<=duration<=15:
            raise ValueError(f'Seedance accepts a 2–15 second reference video; this prepared clip is {duration:.1f} seconds. Use a 2–15 second source clip.')
        if not inp.streams.audio:
            raise ValueError('The prepared Seedance reference has no audio track.')
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('FFmpeg is required to prepare a Seedance-compatible reference video.')
    target=folder/'seedance-reference.mp4'
    filter_graph=(
        f'scale={SEEDANCE_REFERENCE_WIDTH}:{SEEDANCE_REFERENCE_HEIGHT}:force_original_aspect_ratio=decrease,'
        f'pad={SEEDANCE_REFERENCE_WIDTH}:{SEEDANCE_REFERENCE_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=24'
    )
    command=[
        ffmpeg,'-y','-i',str(source),'-map','0:v:0','-map','0:a:0?',
        '-vf',filter_graph,'-c:v','libx264','-pix_fmt','yuv420p','-profile:v','high',
        '-crf','20','-maxrate','6M','-bufsize','12M','-preset','fast',
        '-c:a','aac','-b:a','192k','-movflags','+faststart',str(target),
    ]
    completed=subprocess.run(command,capture_output=True,text=True)
    if completed.returncode:
        raise RuntimeError('Could not encode a Seedance-compatible reference video: '+completed.stderr[-1000:])
    if target.stat().st_size>SEEDANCE_MAX_VIDEO_BYTES:
        raise ValueError('Prepared Seedance reference exceeds Fal\'s 50 MB video-input limit. Use a shorter or less detailed source clip.')
    with av.open(str(target)) as output:
        video=output.streams.video[0]
        encoded_duration=float(output.duration/av.time_base)
        codec=video.codec_context.name
        if (video.width,video.height)!=(SEEDANCE_REFERENCE_WIDTH,SEEDANCE_REFERENCE_HEIGHT) or codec!='h264' or not 2<=encoded_duration<=15:
            raise RuntimeError('Seedance reference validation failed after encoding; no Fal request was submitted.')
    (folder/'seedance-reference.json').write_text(json.dumps({
        'source':source.name,'file':target.name,'width':SEEDANCE_REFERENCE_WIDTH,
        'height':SEEDANCE_REFERENCE_HEIGHT,'duration_seconds':round(encoded_duration,3),
        'codec':'h264','size_bytes':target.stat().st_size,
    },indent=2))
    return target

def prepare_seedance_video(folder, semitones=3):
    """Embed +3-semitone isolated vocals into the colored-depth composite."""
    folder=Path(folder);binary=shutil.which('rubberband')
    if not binary:raise RuntimeError('Rubber Band is required for pitch shifting.')
    pitched=folder/f'vocals-plus{semitones}.wav'
    subprocess.run([binary,'--fine','--pitch',str(semitones),'--time','1',str(folder/'vocals.wav'),str(pitched)],check=True,capture_output=True)
    original=read_audio(folder/'vocals.wav');samples=read_audio(pitched)
    n=original.shape[1]
    samples=np.pad(samples,((0,0),(0,max(0,n-samples.shape[1]))))[:,:n]
    write_audio(pitched,samples)
    target=folder/'seedance-input.mp4'
    with av.open(str(folder/'composite-silent.mp4')) as video,av.open(str(target),'w') as out:
        vs=out.add_stream_from_template(video.streams.video[0]);audio=out.add_stream('aac',rate=RATE);audio.layout='stereo';audio.bit_rate=192000
        for packet in video.demux(video=0):
            if packet.dts is not None:packet.stream=vs;out.mux(packet)
        for i in range(0,n,4096):
            f=av.AudioFrame.from_ndarray(np.ascontiguousarray(samples[:,i:i+4096]),format='fltp',layout='stereo');f.sample_rate=RATE;f.pts=i
            for packet in audio.encode(f):out.mux(packet)
        for packet in audio.encode():out.mux(packet)
    manifest=folder/'audio-manifest.json'
    data=json.loads(manifest.read_text()) if manifest.exists() else {}
    data.update(seedance_video='seedance-input.mp4',seedance_audio=None,pitch_semitones=semitones,embedded_vocals=f'vocals-plus{semitones}.wav',final_audio='entire original source audio')
    manifest.write_text(json.dumps(data,indent=2))
    return target
