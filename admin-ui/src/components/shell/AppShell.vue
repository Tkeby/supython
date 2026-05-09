<script setup lang="ts">
import { NLayout, NLayoutSider, NLayoutHeader, NLayoutContent } from 'naive-ui'
import SideNav from './SideNav.vue'
import TopBar from './TopBar.vue'
import { useUiStore } from '@/stores/ui'
const ui = useUiStore()
</script>

<template>
  <NLayout has-sider style="height: 100vh">
    <NLayoutSider
      :collapsed="ui.navCollapsed" collapse-mode="width"
      :width="240" :collapsed-width="64" bordered
    >
      <SideNav />
    </NLayoutSider>
    <NLayout>
      <NLayoutHeader bordered><TopBar /></NLayoutHeader>
      <NLayoutContent style="padding: 24px"><RouterView /></NLayoutContent>
    </NLayout>
  </NLayout>
</template>