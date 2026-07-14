**To:** Squarespace Domains support
**Subject:** Nameserver change not propagating to registry — evanmayo-wilson.org

Hello,

I need help with a nameserver change on my domain **evanmayo-wilson.org** that has not taken effect at the registry.

On July 14 I switched the domain from custom nameservers to Squarespace nameservers. In **Settings → Domains → evanmayo-wilson.org → Domain Nameservers**, the page confirms the change ("Nameservers updated on Jul 14, 2026, 3:41 PM") and now lists only:

- ns01.squarespacedns.com
- ns02.squarespacedns.com
- ns03.squarespacedns.com
- ns04.squarespacedns.com

However, well beyond the propagation window, public DNS still shows the domain delegated to the previous custom nameservers as well:

- dns1.p05.nsone.net
- dns2.p05.nsone.net
- dns3.p05.nsone.net
- dns4.p05.nsone.net

A public NS lookup for evanmayo-wilson.org returns all eight nameservers (the four squarespacedns.com plus the four nsone.net), so resolvers are still reaching the old zone. As a result, my DNS Settings page continues to show the banner "You're using custom nameservers," my custom records are not fully active, and www.evanmayo-wilson.org still resolves to the old site instead of the A/CNAME records I have configured.

I believe the registry delegation update is stuck. The domain currently has the status codes **clientTransferProhibited** and **clientUpdateProhibited** — could one of these be preventing the nameserver update from being pushed to the .org registry?

Could you please:

1. Confirm what nameservers are currently set at the registry for evanmayo-wilson.org, and
2. Force/re-push the delegation so that only the four squarespacedns.com nameservers are authoritative, removing the nsone.net entries.

For reference, the records I have configured in DNS Settings (which should become active once the domain is fully on Squarespace nameservers) are:

- A @ 185.199.108.153
- A @ 185.199.109.153
- A @ 185.199.110.153
- A @ 185.199.111.153
- CNAME www → evanmayo-wilson.github.io
- TXT _github-pages-challenge-EvanMayo-Wilson → (GitHub Pages verification)

I am pointing the domain at GitHub Pages. I do not want to transfer the domain — I just need the nameserver delegation to reflect the Squarespace nameservers already shown in my account.

Thank you,
Evan Mayo-Wilson
evan.mayowilson@gmail.com
