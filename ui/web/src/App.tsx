// 壳：左边地方栏（首页 / 编辑台 / 设置三个键），右边是此刻的地方（外层 #58 #64 #70 #79 #104 #111 #136）。
// 页面先认项目（一个项目一位助理，P-15）：首页是项目墙，点一个进项目页——正中间一只对话输入框、底下这个项目的工作区；
// 点一行进工作区页——看板 / 文件两个镜头，对话在右边那块板上（还是项目的那一段）。编辑台是全局一个流程库、有自己的对话，
// 和项目的世界平行（P-16）。设置（P-25）是全局的一块，开着时地方的页眉让开。每次打开都从首页进，不记上次在哪。
// 换地方不闪：每种数据上次那份记着先摆上（lib/lastSeen），全站的图一起来就预热（lib/pictures）。
// 页面只是 `ai4sci serve` 的客户端。
import { useEffect, useState } from 'react'

import { api } from '@/api/client'
import { ASSETS } from '@/assets'
import { ErrorNote } from '@/components/bits'
import { Scene } from '@/components/Scene'
import { Top } from '@/components/Top'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Home } from '@/home/Home'
import { NewProject } from '@/home/NewProject'
import { useMediaQuery, WIDE } from '@/lib/useMediaQuery'
import { preloadPictures } from '@/lib/pictures'
import { useResource } from '@/lib/useResource'
import { HOME, type Place, type PlacesProps, projectOf } from '@/places/place'
import { PlacesSheet } from '@/places/PlacesSheet'
import { Rail } from '@/places/Rail'
import { ProjectPlace } from '@/project/ProjectPlace'
import { SettingsBoard } from '@/settings/SettingsBoard'
import { StudioPlace } from '@/studio/StudioPlace'

export default function App() {
  const projects = useResource(api.projects, [], 'projects')
  const health = useResource(api.health, [])
  // 每家 agent 的旋钮清单与新对话用的值（外层 #86，P-25）：对话用哪家就摆哪家的；设置里改了缺省要重拉
  const backends = useResource(api.backends, [], 'backends')
  useEffect(preloadPictures, [])
  const [settingsOpen, setSettingsOpen] = useState(false)
  const settingsDot = health.data ? health.data.checks_ok === false : false
  // 删了东西之后目录外没清干净的几句（CLI 那边的会话、机器上的镜像），摆在正文顶上，点一下收
  const [leftovers, setLeftovers] = useState<string[]>([])
  const [picked, setPlace] = useState<Place>(HOME)
  const wide = useMediaQuery(WIDE)
  const healthy = health.loading && !health.data ? null : health.data?.ok === true
  // 站着的项目已经不在了（另一处删了、换了数据根）：当作在首页。清单还没回来时不挂项目——不能先去取，取回 404 再跳
  const inside = projectOf(picked)
  const known = projects.data !== null && inside !== null && projects.data.some((p) => p.id === inside)
  const stale = projects.data !== null && inside !== null && !known
  const place: Place = stale ? HOME : picked

  const go = (next: Place) => {
    setPlace(next)
    setSettingsOpen(false)
  }
  const places: PlacesProps = {
    place,
    onHome: () => go(HOME),
    onStudio: () => go({ kind: 'studio' }),
    settingsOpen,
    settingsDot,
    onSettings: () => setSettingsOpen((open) => !open),
  }
  const menu = wide ? undefined : <PlacesSheet {...places} />
  // 设置里检查过、改过：/health 的那一位与每家新对话用的值都可能变了
  const settingsChanged = () => { void health.reload(); void backends.reload() }

  return (
    <TooltipProvider>
      <div className="flex h-dvh overflow-hidden">
        {wide && <Rail {...places} />}
        <div className="flex min-w-0 flex-1 flex-col">
          {leftovers.length > 0 && (
            <button type="button" onClick={() => setLeftovers([])} className="w-full text-left">
              <ErrorNote text={`本机已删，没清干净的：${leftovers.join('；')}`} className="rounded-none" />
            </button>
          )}
          {settingsOpen
            ? (
              <>
                {/* 设置是全局的，不挂在哪个地方底下（主人 2026-09-22）：宽屏没有页眉，窄屏只留一条放地方清单的入口 */}
                {!wide && <Top menu={menu} title="设置" />}
                <div className="relative flex min-h-0 flex-1">
                  <Scene picture={ASSETS.board} veil="mist" />
                  <SettingsBoard onClose={() => setSettingsOpen(false)} onChanged={settingsChanged} />
                </div>
              </>
            )
            : place.kind === 'home'
              ? <Home projects={projects} menu={menu} onOpen={(id) => go({ kind: 'project', id })} onNew={() => go({ kind: 'door' })} />
              : place.kind === 'door'
                ? <NewProject existing={projects.data ?? []} menu={menu}
                              onCreated={async (id) => { await projects.reload(); go({ kind: 'project', id }) }}
                              onCancel={() => go(HOME)} />
                : place.kind === 'studio'
                  ? <StudioPlace healthy={healthy} backends={backends.data} menu={menu} />
                  : inside && known && (
                    // 换项目就重建整个世界（对话、清单都按项目隔离）；项目页与它的工作区页之间来回不重建
                    <ProjectPlace key={inside} projectId={inside} summary={projects.data?.find((p) => p.id === inside) ?? null}
                                  wsId={place.kind === 'workspace' ? place.id : null}
                                  healthy={healthy} backends={backends.data} menu={menu}
                                  onOpenWorkspace={(id) => go({ kind: 'workspace', project: inside, id })}
                                  onBack={() => go({ kind: 'project', id: inside })}
                                  onRemoved={async (rest) => { setLeftovers(rest); await projects.reload(); go(HOME) }}
                                  onWorkspaceRemoved={async (rest) => { setLeftovers(rest); await projects.reload(); go({ kind: 'project', id: inside }) }} />
                  )}
        </div>
      </div>
    </TooltipProvider>
  )
}
