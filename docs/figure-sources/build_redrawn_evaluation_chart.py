"""Redraw the existing report's numeric chart without altering its values."""
from pathlib import Path
import csv
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / 'figures'
SOURCE = Path(__file__).resolve().parent
FIGURES.mkdir(parents=True, exist_ok=True)
SOURCE.mkdir(parents=True, exist_ok=True)

font_path = Path(r'C:\Windows\Fonts\msyh.ttc')
font_manager.fontManager.addfont(str(font_path))
plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font_path).get_name(),
                     'axes.unicode_minus':False, 'svg.fonttype':'none', 'font.size':12})

rows = [
 ('EDF',67.55,.4362,.9481,34962),
 ('优先级 EDF',68.26,.4417,.9550,37474),
 ('确定性规划',69.88,.4297,.9007,35954),
 ('耗时概率',75.13,.3899,.8494,315187),
 ('全局概率',75.31,.3881,.8598,328762),
 ('个性化',74.03,.3953,.8377,320860),
 ('风险感知',74.58,.3874,.8355,317024),
 ('ChronoFlow',79.90,.3770,.7516,165329),
]
with (SOURCE/'历史回放主表.csv').open('w', encoding='utf-8-sig',newline='') as handle:
 writer=csv.writer(handle)
 writer.writerow(['方法','WOTCR百分比','归一化完成延迟','CVaR90','加权扰动成本','可行性百分比'])
 for row in rows:writer.writerow([*row,100])

NAVY='#082A49'; TEAL='#009D90'; GRAY='#9DB4C2'; PURPLE='#7864C8'; MUTED='#63758A'
fig=plt.figure(figsize=(15,7.15),facecolor='white')
fig.text(.045,.942,'历史测试回放：八方法对照',fontsize=24,fontweight='bold',color=NAVY)
fig.text(.045,.895,'350 个测试场景  ·  随机种子 11  ·  同一检查点',fontsize=12.5,color=MUTED)
fig.text(.955,.913,'研究回放',ha='right',va='center',fontsize=12,color=TEAL,
         bbox={'boxstyle':'round,pad=0.5','fc':'#E9F6F3','ec':'none'})

grid=fig.add_gridspec(1,3,left=.155,right=.955,bottom=.21,top=.77,wspace=.19,width_ratios=[1.19,1,1])
y=np.arange(8)
for col,(index,title,limit,ticks) in enumerate([
 (1,'加权按时完成率 ↑',100,[0,25,50,75,100]),
 (3,'尾部截止损失 CVaR90 ↓',1.08,[0,.25,.5,.75,1]),
 (2,'归一化完成延迟 ↓',.51,[0,.1,.2,.3,.4,.5])]):
 ax=fig.add_subplot(grid[0,col])
 ax.axhspan(6.56,7.44,color='#E9F6F3',zorder=0)
 values=[row[index] for row in rows]
 colors=[GRAY]*7+[TEAL]
 if col==0:
  ax.barh(y,values,height=.49,color=colors,zorder=3)
 else:
  for yi,val,color in zip(y,values,colors):
   ax.plot([0,val],[yi,yi],lw=2.3,color='#DBE4EB',zorder=2)
   ax.scatter([val],[yi],s=51 if yi==7 else 35,color=color,zorder=3)
 for yi,val in enumerate(values):
  label=f'{val:.2f}%' if col==0 else f'{val:.4f}'
  ax.annotate(label,(val,yi),xytext=(7,0),textcoords='offset points',va='center',
              fontsize=11,color=TEAL if yi==7 else NAVY,fontweight='bold' if yi==7 else 'normal')
 ax.set_title(title,fontsize=13.3,fontweight='bold',loc='left',pad=20,color=NAVY)
 ax.set_xlim(0,limit);ax.set_ylim(7.7,-.7);ax.set_xticks(ticks)
 ax.xaxis.grid(True,color='#E8EDF1',linewidth=.8,zorder=0)
 ax.tick_params(axis='both',length=0,labelcolor=MUTED,labelsize=10)
 ax.set_yticks(y)
 ax.set_yticklabels([r[0] for r in rows] if col==0 else ['']*8,fontsize=12)
 if col==0:
  ax.get_yticklabels()[-1].set_color(TEAL);ax.get_yticklabels()[-1].set_fontweight('bold')
 ax.tick_params(axis='y',pad=15)
 for spine in ax.spines.values():spine.set_visible(False)

fig.text(.155,.105,'相对 EDF：+12.35 个百分点',fontsize=12,fontweight='bold',color=TEAL)
fig.text(.47,.105,'相对全局概率：+4.59 个百分点',fontsize=12,fontweight='bold',color=PURPLE)
fig.text(.84,.105,'可行性均为 100%',fontsize=12,color=NAVY)
fig.text(.155,.044,'数值沿用技术方案图 10 主表；研究回放结果与真人试用、当前 APK 验收分别解释。',fontsize=10,color=MUTED)
fig.savefig(FIGURES/'eval-replay-chart.png',dpi=200,facecolor='white')
fig.savefig(SOURCE/'eval-replay-chart.svg',facecolor='white')
plt.close(fig)
print('Saved evaluation chart: 3000 x 1430 pixels; numeric source table and editable SVG.')
