# Product specifications and Customer Facing Services

Research date: 21 October 2026. Product managers design what is sold in TMF620; service designers maintain the realization in TMF633. This is a catalogue pattern, not a fixed TM Forum list of CFS names.

## The important boundary

The SID describes a ProductSpecification as the business-facing selection of what marketing wants to sell. For an intangible product it is realized by one or more CustomerFacingServiceSpecifications (CFSS). A CFSS describes the functional service the customer recognizes. A ResourceFacingServiceSpecification (RFSS) describes technical implementation below it. Thus **HSS, packet gateway and SMSC are targets or resources behind a service**, not names of customer-facing services. A physical device such as a modem or handset can be a product/resource without being a CFS.

## Examples supported by TM Forum material

| Product specification or bundle | Possible CFSS | Basis |
| --- | --- | --- |
| Mobile line with allowances | Mobile Line, National Voice Bucket, Data Bucket, SMS Bucket | The IG1228 mobile service catalogue discussion explicitly identifies these as separate CFSs. It also discusses a `requires` dependency from the buckets to Mobile Line. |
| Broadband Internet | Broadband Internet / Internet Access CFS | SID's broadband and cable modem example distinguishes the Internet CFS from the modem resource and its supporting RFSs. |
| Internet plus television | Internet Access and IPTV CFSs | A TM Forum API discussion uses this example and notes an IPTV `reliesOn` relationship to Internet Access. |
| Business VPN | VPN Service / IPsec VPN CFS | SID contains VPNServiceSpecification and IPsecVPNService examples; network routing functions are resource-facing. |

These examples are starting points. A provider may split or combine CFSs differently. The catalogue must store CFS-to-CFS dependencies and versioned characteristic mappings rather than assume every ProductSpecification maps to exactly one CFS.

## Mobile Mini design implication

The product manager sees **Mobile Mini**, its Voice/Data/SMS specifications, allowances and price. A service designer maps it to Mobile Line plus Voice, Data and SMS bucket CFSSs, including dependency on the line. The service designer then maps CFSSs to RFSSs and platform-specific activation steps. The current seed catalogue has three bucket-like CFSs and example HSS, packet gateway and SMSC target metadata; adding Mobile Line and explicit CFS dependencies is the next technical catalogue revision. The current quote preview makes no network changes.

## Sources

- TM Forum SID [ProductSpecification](https://www.tmforum.org/Browsable_HTML_SID_v22.0/html/EARoot/EA2/EA3/EA9/EA1117.htm), [CustomerFacingServiceSpec](https://www.tmforum.org/Browsable_HTML_SID_R20.0/content/_3E3F0EC000E93D9DADDE0194-content.html), and [ResourceFacingServiceSpec](https://www.tmforum.org/Browsable_HTML_SID_R20.0/content/_3E3F0EC000E93D9DADF100B9-content.html).
- TM Forum [IG1228 mobile service catalogue discussion](https://engage.tmforum.org/communities/community-home/digestviewer/viewthread?CommunityKey=d543b8ba-9d3a-4121-85ce-5b68e6c31ce5&GroupId=31&MessageKey=a85e243f-0355-4873-a1ee-fde4ba954400&hlmlt=VT&tab=digestviewer) and [TMFS008 postpaid mobile use case](https://www.tmforum.org/resources/technical-specification/tmfs008-use-case-service-and-resource-order-management-for-postpaid-mobile-subscribers-v3-6-0/).
- TM Forum SID [broadband/modem example](https://www.tmforum.org/Browsable_HTML_SID_v22.0/html/EARoot/EA2/EA5/EA1/EA1/EA1563.htm) and [VPN specification example](https://www.tmforum.org/Browsable_HTML_SID_R20.0/content/_3E3F0EC000E93DAF6A970061-content.html).
- TM Forum community [IPTV and Internet Access CFS relationship example](https://engage.tmforum.org/communities/community-home/digestviewer/viewthread?CommunityKey=d543b8ba-9d3a-4121-85ce-5b68e6c31ce5&MessageKey=8799a5f7-5e6c-46b3-97ee-3082768b57c6&tab=digestviewer).
