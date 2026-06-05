import {
  Button,
  Card,
  Chip,
  Field,
  Logo,
  PageHeader,
  SectionLabel,
  TopBar,
} from '../components';

export function Styleguide() {
  return (
    <div>
      <TopBar>
        <span style={{ fontSize: 12, color: 'var(--color-ink-dim)' }}>styleguide</span>
      </TopBar>
      <PageHeader title="Styleguide" sub="atom 컴포넌트 시각 확인" />
      <div style={{ padding: 32, display: 'flex', flexDirection: 'column', gap: 32 }}>
        <Section label="Logo">
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Logo size={18} />
            <Logo size={26} />
            <Logo size={48} />
          </div>
        </Section>

        <Section label="Button">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <Button>Default</Button>
            <Button variant="primary">Primary</Button>
            <Button variant="danger">Danger</Button>
            <Button disabled>Disabled</Button>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 12 }}>
            <Button size="sm">Small</Button>
            <Button size="md" variant="primary">Medium</Button>
            <Button size="lg" variant="primary">Large</Button>
          </div>
          <div style={{ marginTop: 12, maxWidth: 320 }}>
            <Button full variant="primary">Full width</Button>
          </div>
        </Section>

        <Section label="Chip">
          <div style={{ display: 'flex', gap: 8 }}>
            <Chip>Default</Chip>
            <Chip variant="active">Active</Chip>
            <Chip variant="soft">Soft</Chip>
          </div>
        </Section>

        <Section label="Field">
          <div style={{ display: 'flex', gap: 12, maxWidth: 700, flexWrap: 'wrap' }}>
            <Field label="학기" value="2026-2" dropdown width={200} />
            <Field label="검색어" placeholder="과목명·교수명·키워드..." full />
          </div>
          <div style={{ marginTop: 12, maxWidth: 700 }}>
            <Field label="이수 학점" value="18" suffix="학점" width={200} />
          </div>
        </Section>

        <Section label="Card">
          <Card style={{ maxWidth: 400 }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>객체지향프로그래밍</h3>
            <p style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--color-ink-dim)' }}>
              이대호 교수 · 3학점 · 전공필수
            </p>
            <div style={{ display: 'flex', gap: 6, marginTop: 12 }}>
              <Chip variant="soft">설명력</Chip>
              <Chip variant="soft">과제 중</Chip>
            </div>
          </Card>
        </Section>

        <Section label="SectionLabel (자기 자신)">
          <SectionLabel>Section Label Example</SectionLabel>
        </Section>
      </div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section>
      <SectionLabel>{label}</SectionLabel>
      <div style={{ marginTop: 12 }}>{children}</div>
    </section>
  );
}
