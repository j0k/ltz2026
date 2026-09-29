# Монтаж живой записи: вырезать ожидание, положить голоса на сцены, субтитры, MP4 1080p.
import json, subprocess, sys
S={s['id']:s for s in json.load(open('script.json'))}
T=json.load(open('timeline.json')); cuts=T['cuts']; video=open('video_path.txt').read().strip().replace('/home/jk/exp/LTZ2026/films/kostik_live/','')
def m(t):
    for a,b in cuts:
        if t>=b: t-=(b-a)
        elif t>a: t=a
    return t
dur=float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',video],capture_output=True,text=True).stdout)
keep=[]; cur=0
for a,b in cuts: keep.append((cur,a)); cur=b
keep.append((cur,dur))
def ts(x):
    ms=int(round(x*1000)); return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"
srt=[]; delays=[]
for i,sc in enumerate(T['scenes'],1):
    st,en=m(sc['start']),m(sc['end']); a=st+0.25; delays.append(int(a*1000))
    srt.append(f"{i}\n{ts(st+0.15)} --> {ts(min(en-0.1,a+S[sc['id']]['dur']+0.6))}\n{S[sc['id']]['caption']}\n")
open('subs.srt','w').write("\n".join(srt))
vf=[f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{k}]" for k,(a,b) in enumerate(keep)]
vf.append("".join(f"[v{k}]" for k in range(len(keep)))+f"concat=n={len(keep)}:v=1:a=0[vc]")
style="FontName=DejaVu Sans,FontSize=15,PrimaryColour=&H00FFFFFF,BackColour=&H99101828,OutlineColour=&H99101828,BorderStyle=3,Outline=6,Shadow=0,MarginV=34"
vf.append(f"[vc]fps=30,subtitles=subs.srt:force_style='{style}'[vout]")
ids=[sc['id'] for sc in T['scenes']]
for j,(sid,dl) in enumerate(zip(ids,delays),1): vf.append(f"[{j}:a]aresample=48000,adelay={dl}|{dl}[a{j}]")
vf.append("".join(f"[a{j}]" for j in range(1,len(ids)+1))+f"amix=inputs={len(ids)}:normalize=0,alimiter=limit=0.95[aout]")
out=sys.argv[1] if len(sys.argv)>1 else 'kostik_demo_live.mp4'
cmd=['ffmpeg','-v','error','-y','-i',video]+sum([['-i',f'voice/{sid}.mp3'] for sid in ids],[])+['-filter_complex',";".join(vf),'-map','[vout]','-map','[aout]',
     '-c:v','libx264','-preset','veryfast','-crf','22','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-shortest','-movflags','+faststart',out]
r=subprocess.run(cmd,capture_output=True,text=True); print('rc',r.returncode,r.stderr[-600:])
