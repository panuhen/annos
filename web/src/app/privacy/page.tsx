import type { Metadata } from "next";

import { ContactEmail } from "@/components/contact-email";
import { LegalLayout } from "@/components/legal-layout";

export const metadata: Metadata = {
  title: "Privacy Policy · Annos",
  description: "What personal data Annos processes, and the minimisation behind it.",
};

export default function PrivacyPage() {
  return (
    <LegalLayout title="Privacy Policy" lastUpdated="2026-08-08">
      <section>
        <h2>1. Who we are</h2>
        <p>
          Annos is a free,{" "}
          <a href="https://github.com/panuhen/annos" rel="noopener">
            open-source
          </a>{" "}
          food, exercise and weight tracker, usable on the web and from an AI client connected over
          MCP. This policy explains what personal data the
          hosted service at annos.app processes and why, under the EU General Data Protection
          Regulation (GDPR). Annos is operated from Finland, and personal data is stored and
          processed in the European Union.
        </p>
      </section>

      <section>
        <h2>2. The short version: as little as possible</h2>
        <p>
          Annos is built to know as little about you as it can, precisely because what you track
          here is health data. It never asks for your real name — inside the app you are only a
          nickname the system generates for you. It runs no analytics and no tracking, shows ads
          to no one, and never sells or shares your data. It gives no advice: it returns your own
          numbers back to you, and nothing more.
        </p>
      </section>

      <section>
        <h2>3. What we collect</h2>
        <p>
          <strong>To sign you in.</strong> Your email address, and either a password (kept only as
          a salted hash, never in readable form) or, if you choose Google sign-in, a Google account
          identifier. If you use Google, Google also sends your name and profile photo; Annos
          discards both immediately and stores neither.
        </p>
        <p>
          <strong>Your email is quarantined.</strong> Your address is held only by the sign-in
          system, kept separate from everything you log. The part of Annos that stores your food,
          exercise and weight has no access to it — this is enforced by a database permission, not
          just a promise, so the two cannot be joined back together by an ordinary mistake.
        </p>
        <p>
          <strong>Your profile.</strong> The generated nickname (the only name Annos uses), and the
          figures the calculations need: birth year (not a full date of birth), height, sex,
          timezone, and your unit preference.
        </p>
        <p>
          <strong>What you log.</strong> The meals, foods, exercise, body weight and body
          measurements you record, plus any free-text notes you add. This is health-related data —
          see Section 4.
        </p>
        <p>
          <strong>Automatically.</strong> Ordinary server logs, which record no IP address. Your IP
          address is used only transiently, at the security layer, to rate-limit sign-in and
          account-recovery attempts and prevent abuse — it is never attached to your account or to
          anything you log. There is no analytics, tracking, or advertising technology anywhere in
          Annos.
        </p>
      </section>

      <section>
        <h2>4. Health data</h2>
        <p>
          What you log — food, weight, exercise, body measurements, and anything you disclose in a
          free-text note — is health-related data, a special category under GDPR Article 9. Annos
          processes it only to provide the tracking features you use, on the basis of your{" "}
          <strong>explicit consent</strong>, given when you choose to log it. It is never sold,
          never shared beyond the infrastructure providers in Section 7, and{" "}
          <strong>never used to train machine-learning models</strong>. This is the reason for the
          minimisation and the email quarantine above: the less that is stored, and the more it is
          kept apart from anything identifying, the better this data is protected.
        </p>
      </section>

      <section>
        <h2>5. Legal bases</h2>
        <ul>
          <li>Performing our agreement with you, to run your account and the service (Art. 6(1)(b)).</li>
          <li>Your explicit consent, for the health data you log (Art. 9(2)(a)).</li>
          <li>Our legitimate interest in keeping the service secure and preventing abuse (Art. 6(1)(f)).</li>
          <li>Compliance with legal obligations, where any apply (Art. 6(1)(c)).</li>
        </ul>
        <p>Annos does not profile you and makes no automated decisions with legal or similarly significant effects.</p>
      </section>

      <section>
        <h2>6. Email we send</h2>
        <p>
          Annos sends only two kinds of email: a confirmation link when you register, and a
          password-reset link when you ask for one. There are no newsletters and no marketing. Only
          your address and the link are sent — never any of the data you have logged.
        </p>
      </section>

      <section>
        <h2>7. Who else processes data</h2>
        <p>To run the service we rely on a small number of providers, acting on our instructions:</p>
        <ul>
          <li>Cloud hosting and database, in the European Union (Hetzner).</li>
          <li>A network and security layer in front of the service, which processes connection data such as your IP address (Cloudflare).</li>
          <li>Transactional email, to send the two messages above — it receives your email address, and may process it outside the EU under the EU-US Data Privacy Framework or standard contractual clauses (Resend).</li>
          <li>Google Sign-In, only if you choose it, under the EU-US Data Privacy Framework (Google).</li>
        </ul>
        <p>
          We do not sell personal data, and we do not share it with anyone else except where the law
          requires it. None of the data you log ever leaves the European Union.
        </p>
      </section>

      <section>
        <h2>8. How long we keep it</h2>
        <ul>
          <li>Your account and everything in it are kept while your account exists.</li>
          <li>When you delete your account, it and all your data are erased immediately and permanently — there is no soft delete and no grace period.</li>
          <li>Encrypted backups are kept for up to 30 days and then overwritten; they are never restored for one person.</li>
          <li>Server logs are short-lived and record no IP address. Your IP is used only to rate-limit sign-in and recovery, in short windows, and is never linked to your account or the data you log. The network layer in front of the service (Section 7) processes IP addresses under its own retention.</li>
        </ul>
      </section>

      <section>
        <h2>9. Your rights</h2>
        <p>
          Under the GDPR you can ask to access, correct, erase, restrict, or port your data, object
          to processing, and withdraw consent. Two of these are built directly into the app: from
          your profile page you can <strong>export all of your data</strong> as a file, and{" "}
          <strong>delete your account and everything in it</strong>, at any time, without asking.
        </p>
        <p>
          For anything else, contact us (Section 12) and we will respond within one month. You also
          have the right to complain to a supervisory authority — in Finland, the Office of the Data
          Protection Ombudsman (tietosuoja.fi), or your local authority elsewhere in the EU/EEA.
        </p>
      </section>

      <section>
        <h2>10. Cookies</h2>
        <p>
          Annos uses only strictly necessary cookies: one to keep you signed in, and a small one
          remembering your chosen language. Your theme choice is kept in your browser, not in a
          cookie. There are no analytics or advertising cookies.
        </p>
      </section>

      <section>
        <h2>11. Security and children</h2>
        <p>
          Data is encrypted in transit (TLS) and at rest, access follows least privilege (the email
          quarantine is one example), and the service is logged and reviewed. No system is perfectly
          secure; if you believe your account has been compromised, contact us. Annos is not
          directed to children under 16, and we do not knowingly collect their data.
        </p>
      </section>

      <section>
        <h2>12. Contact and changes</h2>
        <p>
          For any privacy question, or to exercise a right, contact us at <ContactEmail />. We may
          update this policy; where a change is material we will make it visible in the app, and
          continued use after it takes effect means you accept it.
        </p>
        <p className="fine">
          Food and nutrient data is from Fineli, Finnish Institute for Health and Welfare, licensed
          under CC BY 4.0. Activity energy costs are from the 2024 Adult Compendium of Physical
          Activities (Herrmann et al.),{" "}
          <a href="https://pacompendium.com" rel="noopener">
            pacompendium.com
          </a>
          .
        </p>
      </section>
    </LegalLayout>
  );
}
