<script setup lang="ts">
import { NConfigProvider, NGlobalStyle, darkTheme } from 'naive-ui'
</script>

<template>
  <NConfigProvider :theme="darkTheme">
    <NGlobalStyle />
    <RouterView />
  </NConfigProvider>
</template>
