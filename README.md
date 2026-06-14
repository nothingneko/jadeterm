
# jadeterm
bullshit free terminal built by catgirls

## what does "bullshit free" mean?
jadeterm isn't built by nazis, isn't "container native", isn't ugly as piss, 
doesn't have a million config options, isn't built by nazis, 
and i only used claude a little bit.

## what even is jadeterm?
jadeterm is a terminal

it runs on your computer, or in a flatpak

the container workflow works in the flatpak

it looks kinda in-place on your desktop, the plasma titlebar appears on plasma, it's libadw though, if you don't like libadwaita, sorry, cope

it's seriously just a terminal

## so is this suckless?

no, see "[jadeite] isn't built by nazis"

## can i configure it?

you can set the theme, the startup command, and three keyboard shortcuts

the config file is yaml, if you don't like it, we aren't friends anymore

```
integration:
    break-claude: disabled
    prefer-dark: yes
	
theme:
    light: breeze
    dark:  breeze-dark
	
keyboard:
    new-tab: ctrl+shift+tab
    close tab: ctrl+shift+w
    quit app: super+q
```
- add the `startup` option and define it to change the startup command

- `prefer-dark` is whether or not the xdg dark/light theme is obeyed, just set it to yes to make it always dark.

- `break-claude` breaks claude code, none of the other agents are broken because they aren't worth a damn.

- `theme` is what's on the tin.

- keyboard shortcuts, there's only three of them, just type what they are, super is the windows key, alt is alt.

- the terminal bell is delivered through standardized notifications, 
you can turn it off by revoking the notification permission. if for some reason you can't revoke the notification permission, get with the times.

- no, there isn't transparency

everything else is up to your shell

### what about [insert thing not listed]?

jadeterm isn't for you, consider coping, or asking nicely
